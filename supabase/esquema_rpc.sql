-- ============================================================================
-- esquema_rpc.sql — NSAC, rama `supabase-candidatos`
-- ESQUEMA + BUSCADOR DE SIMILITUD PONDERADA (K-NN) para Supabase (PostgreSQL).
--
-- DÓNDE SE EJECUTA: panel de Supabase -> SQL Editor -> pegar TODO este
-- archivo y ejecutar. Es idempotente (CREATE IF NOT EXISTS / OR REPLACE):
-- se puede re-ejecutar sin perder datos.
--
-- QUÉ CREA:
--   1) tabla sitios_candidatos  — el catálogo pre-calculado (sube
--      `poblador_supabase.py`), con las claves del `resumen` unificado del
--      proyecto (mismas unidades: m, grados, K, 0-1, W/m²).
--   2) tabla parametros_escalas — rangos físicos de normalización (una fila
--      por parámetro del resumen). Puedes afinar los rangos sin tocar la
--      función.
--   3) calcular_similitud(perfil_ideal JSONB, datos_lugar RECORD)
--      — distancia euclidiana inversa normalizada (0..1, 1 = idéntico).
--   4) buscar_analogos_ponderados(parametros JSONB, objetivo_espacial TEXT)
--      — RPC que devuelve el Top 1 extraterrestre + el Top 5 de la Tierra.
--
-- CONVENCIÓN DE DATOS HONESTOS (regla de oro del proyecto): un NULL
-- significa "la fuente no dio el dato" y NUNCA se inventa. La similitud
-- ignora los parámetros NULL y renormaliza los pesos de los que sí hay.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) Tabla del catálogo
-- ---------------------------------------------------------------------------

create table if not exists sitios_candidatos (
    id                      bigserial primary key,
    sitio_id                text unique not null,   -- 'tierra@-24.08,-69.47±0.05'
    cuerpo                  text not null
                            check (cuerpo in ('tierra', 'luna', 'marte')),
    nombre                  text,
    tipo                    text,        -- tipo de formación (Gazetteer) / descripción
    lat                     double precision not null,
    lon                     double precision not null,
    radio_grados            double precision not null default 0.05,
    -- resumen unificado del proyecto (claves de _resumen_para_registro);
    -- NULL = esa fuente no aportó el dato en esta consulta
    elevacion_media_m       double precision,
    pendiente_media_grados  double precision,
    rugosidad_media_m       double precision,
    temperatura_media_k     double precision,
    diferencia_dia_noche_k  double precision,
    variacion_estacional_k  double precision,
    reflectancia_media      double precision,
    energia_solar_media_wm2 double precision,
    fraccion_diurna         double precision,
    n_puntos_lola           bigint,      -- píxeles del DTM o puntos LOLA (alias histórico)
    n_observaciones_diviner bigint,
    via_topografia          text,        -- glo30|glo90|dtm_kaguya|dtm_mro|lola_gds
    fecha_consulta          text,        -- ISO tal como vino del registro local
    extra                   jsonb default '{}'::jsonb,  -- resto de metadatos
    actualizado             timestamptz not null default now()
);

create index if not exists idx_candidatos_cuerpo on sitios_candidatos (cuerpo);
create index if not exists idx_candidatos_coordenadas
    on sitios_candidatos (lat, lon);

-- ---------------------------------------------------------------------------
-- 2) Rangos físicos para la normalización (afinables sin tocar la función)
-- ---------------------------------------------------------------------------
-- Rango razonable de cada parámetro entre los tres cuerpos del proyecto.
-- La normalización divide la diferencia absoluta por el ancho del rango:
-- así metros, grados, kelvin y fracciones pesan lo mismo antes de
-- aplicar los pesos del perfil.

create table if not exists parametros_escalas (
    parametro  text primary key,
    valor_min  double precision not null,
    valor_max  double precision not null
);

insert into parametros_escalas (parametro, valor_min, valor_max) values
    ('elevacion_media_m',       -11000.0, 9000.0),   -- fosa + Everest
    ('pendiente_media_grados',      0.0,    60.0),
    ('rugosidad_media_m',           0.0,    50.0),
    ('temperatura_media_k',        20.0,   340.0),   -- PSR lunar polar + valle
    ('diferencia_dia_noche_k',     0.0,   250.0),   -- Luna: ~193 K de ciclo
    ('variacion_estacional_k',     0.0,   250.0),
    ('reflectancia_media',         0.0,     1.0),
    ('energia_solar_media_wm2',    0.0,  1361.0),   -- constante solar
    ('fraccion_diurna',            0.0,     1.0)
on conflict (parametro) do nothing;   -- re-ejecutar NO pisa rangos afinados

-- ---------------------------------------------------------------------------
-- 3) Función de similitud (distancia euclidiana inversa, 0..1)
-- ---------------------------------------------------------------------------
-- perfil_ideal: {"parametro": {"valor": objetivo, "peso": w}, ...}
--   Los pesos NO hace falta que sumen 1 (se renormalizan dentro).
-- datos_lugar: una fila de sitios_candidatos (record).
-- Devuelve: 1 = idéntico al perfil; 0 = distancia máxima; NULL si la fila
--   no tiene ninguno de los parámetros pedidos (no hay nada que comparar).
--
-- d_pond = sqrt( sum_i w_i * ((v_i - objetivo_i) / rango_i)^2 / sum_i w_i )
-- similitud = 1 - d_pond   (los pesos renormalizados hacen que d_pond
--   esté típicamente en 0..1; se recorta a [0,1] por honestidad)

create or replace function calcular_similitud(perfil_ideal jsonb,
                                              datos_lugar record)
returns double precision
language plpgsql immutable
as $$
declare
    suma_pesos   double precision := 0;
    suma_cuadros double precision := 0;
    peso         double precision;
    objetivo     double precision;
    ancho        double precision;
begin
    if perfil_ideal is null then
        return null;
    end if;

    -- En plpgsql no se puede indexar un record por clave dinámica, así que
    -- los campos se leen uno a uno (son EXACTAMENTE las columnas del
    -- resumen unificado del proyecto). Para cada parámetro: aporta a la
    -- distancia solo si su peso está en el perfil (>0) y su valor en la
    -- fila no es NULL (regla de oro: no hay dato -> no se compara, y los
    -- pesos de los parámetros presentes se renormalizan solos al dividir
    -- por suma_pesos).
    -- elevación
    if perfil_ideal ? 'elevacion_media_m'
       and datos_lugar.elevacion_media_m is not null then
        peso := nullif(perfil_ideal->'elevacion_media_m'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'elevacion_media_m'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas where parametro = 'elevacion_media_m';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.elevacion_media_m - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- pendiente
    if perfil_ideal ? 'pendiente_media_grados'
       and datos_lugar.pendiente_media_grados is not null then
        peso := nullif(perfil_ideal->'pendiente_media_grados'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'pendiente_media_grados'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas where parametro = 'pendiente_media_grados';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.pendiente_media_grados - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- rugosidad
    if perfil_ideal ? 'rugosidad_media_m'
       and datos_lugar.rugosidad_media_m is not null then
        peso := nullif(perfil_ideal->'rugosidad_media_m'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'rugosidad_media_m'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas where parametro = 'rugosidad_media_m';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.rugosidad_media_m - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- temperatura
    if perfil_ideal ? 'temperatura_media_k'
       and datos_lugar.temperatura_media_k is not null then
        peso := nullif(perfil_ideal->'temperatura_media_k'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'temperatura_media_k'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas where parametro = 'temperatura_media_k';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.temperatura_media_k - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- día/noche
    if perfil_ideal ? 'diferencia_dia_noche_k'
       and datos_lugar.diferencia_dia_noche_k is not null then
        peso := nullif(perfil_ideal->'diferencia_dia_noche_k'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'diferencia_dia_noche_k'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas
                where parametro = 'diferencia_dia_noche_k';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.diferencia_dia_noche_k - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- estacional
    if perfil_ideal ? 'variacion_estacional_k'
       and datos_lugar.variacion_estacional_k is not null then
        peso := nullif(perfil_ideal->'variacion_estacional_k'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'variacion_estacional_k'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas
                where parametro = 'variacion_estacional_k';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.variacion_estacional_k - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- reflectancia
    if perfil_ideal ? 'reflectancia_media'
       and datos_lugar.reflectancia_media is not null then
        peso := nullif(perfil_ideal->'reflectancia_media'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'reflectancia_media'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas where parametro = 'reflectancia_media';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.reflectancia_media - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- energía solar
    if perfil_ideal ? 'energia_solar_media_wm2'
       and datos_lugar.energia_solar_media_wm2 is not null then
        peso := nullif(perfil_ideal->'energia_solar_media_wm2'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'energia_solar_media_wm2'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas
                where parametro = 'energia_solar_media_wm2';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.energia_solar_media_wm2 - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;
    -- fracción diurna
    if perfil_ideal ? 'fraccion_diurna'
       and datos_lugar.fraccion_diurna is not null then
        peso := nullif(perfil_ideal->'fraccion_diurna'->>'peso', '')
                ::double precision;
        if peso is not null and peso > 0 then
            objetivo := (perfil_ideal->'fraccion_diurna'->>'valor')
                        ::double precision;
            select valor_max - valor_min into ancho
                from parametros_escalas where parametro = 'fraccion_diurna';
            suma_pesos := suma_pesos + peso;
            suma_cuadros := suma_cuadros + peso
                * power((datos_lugar.fraccion_diurna - objetivo)
                        / nullif(ancho, 0), 2);
        end if;
    end if;

    -- Sin ningún parámetro comparable: no hay similitud que calcular.
    if suma_pesos = 0 then
        return null;
    end if;

    return greatest(0, least(1, 1 - sqrt(suma_cuadros / suma_pesos)));
end;
$$;

-- ---------------------------------------------------------------------------
-- 4) RPC de búsqueda (la que llama el cliente: .rpc('buscar_analogos_ponderados'))
-- ---------------------------------------------------------------------------
-- parametros JSONB:
--   {"perfil": {"pendiente_media_grados": {"valor": 5, "peso": 0.8},
--               "elevacion_media_m":      {"valor": -1500, "peso": 0.2}}}
--   (si el JSON no trae la clave 'perfil', se usa el JSON entero como perfil)
-- objetivo_espacial TEXT: cuerpo del sitio que se quiere evaluar
--   ('tierra' | 'luna' | 'marte'; NULL = 'tierra').
--   - extraterrestre_top1: el mejor de los cuerpos EXTERIORES al objetivo
--     (si el objetivo es de la Tierra: entre luna y marte; si es de la
--     Luna: marte; si es de Marte: luna).
--   - tierra_top5: los 5 mejores análogos terrestres.
-- Devuelve JSONB con ambos, el perfil aplicado y el número de filas vistas.

create or replace function buscar_analogos_ponderados(parametros jsonb,
                                                      objetivo_espacial text)
returns jsonb
language plpgsql stable
as $$
declare
    perfil       jsonb := coalesce(nullif(parametros->>'perfil', '')::jsonb,
                                   parametros);
    objetivo     text  := coalesce(objetivo_espacial, 'tierra');
    top_espacial jsonb;
    top_tierra   jsonb;
    n_espacial   int;
    n_tierra     int;
begin
    -- --- Top 1 extraterrestre (excluye el cuerpo objetivo) ----------------
    select to_jsonb(s) || jsonb_build_object(
               'similitud', calcular_similitud(perfil, s))
        into top_espacial
        from sitios_candidatos s
        where s.cuerpo <> 'tierra'
          and s.cuerpo <> objetivo
        order by calcular_similitud(perfil, s) desc nulls last
        limit 1;
    get diagnostics n_espacial = row_count;

    -- --- Top 5 de la Tierra ----------------------------------------------
    select coalesce(jsonb_agg(
                       to_jsonb(s) || jsonb_build_object(
                           'similitud', calcular_similitud(perfil, s))
                       order by calcular_similitud(perfil, s) desc),
                   '[]'::jsonb)
        into top_tierra
        from (select s
              from sitios_candidatos s
              where s.cuerpo = 'tierra'
              order by calcular_similitud(perfil, s) desc nulls last
              limit 5) s;
    get diagnostics n_tierra = row_count;

    return jsonb_build_object(
        'objetivo_espacial', objetivo,
        'perfil_aplicado', perfil,
        'candidatos_espaciales_vistos', n_espacial,
        'candidatos_tierra_vistos', n_tierra,
        'extraterrestre_top1', top_espacial,
        'tierra_top5', top_tierra);
end;
$$;

-- ---------------------------------------------------------------------------
-- 5) (Opcional) RLS: la tabla es de lectura pública, escritura solo por la
--    service key del poblador. Descomenta si el proyecto activa RLS:
--
-- alter table sitios_candidatos enable row level security;
-- create policy "lectura publica" on sitios_candidatos
--     for select using (true);
--
-- NOTA sobre la KEY del poblador: usar la 'service_role' key (sk_...) SOLO
-- en el .env local — esa key salta RLS y puede escribir.
-- ---------------------------------------------------------------------------
