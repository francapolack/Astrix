-- ============================================================================
-- rpc_v2.sql — NSAC, rama `supabase-candidatos` — V2 DEL BUSCADOR
--
-- DÓNDE: panel de Supabase -> SQL Editor -> pegar y ejecutar DESPUÉS de
-- `esquema_rpc.sql` (no lo sustituye: lo extiende con los mismos objetos
-- idempotentes). Re-ejecutar es seguro.
--
-- QUÉ AÑADE:
--   1) similitud_ponderada(perfil JSONB, datos JSONB) — la MISMA fórmula
--      euclidiana inversa del esquema base, pero genérica: recorre las
--      claves del perfil con jsonb_each (nada de un bloque por columna),
--      así acepta CUALQUIER parámetro presente en `parametros_escalas`.
--      Regla de oro intacta: valor NULL en la fila = el parámetro se
--      excluye y los pesos se renormalizan solos.
--   2) similitudes_por_categoria(perfil JSONB, datos JSONB) — el desglose
--      flexible que pide la Tierra: similitud INDEPENDIENTE por categoría
--      (topografia / termico / superficie / iluminacion) + 'global'.
--      Cada categoría renormaliza SUS pesos entre los parámetros que la
--      fila tiene; si no tiene ninguno, NULL (no se inventa).
--   3) buscar_analogo_cuerpo(parametros JSONB, cuerpo TEXT, topn INT) —
--      la "API propia" de cada cuerpo: Top N (default 1) de SOLO ese
--      cuerpo con el desglose por categorías. P.ej.
--        select buscar_analogo_cuerpo('{"perfil":{...}}', 'luna', 1);
--   4) buscar_analogos_v2(parametros JSONB) — la búsqueda completa en UNA
--      llamada: luna_top1 + marte_top1 (cada uno con su API interna) +
--      tierra_top5, todo con desglose por categorías.
--   5) uso_bd() — guardián del límite de almacenamiento del plan Free
--      (500 MB): bytes de la base, bytes de la tabla y nº de filas.
--      El poblador lo consulta antes de cada lote y SE DETIENE al acercarse
--      al límite (la orden de subida es por PRIORIDAD: tierra -> luna ->
--      marte, así lo primero valioso ya está dentro cuando se corta).
--
-- NOTA DE CAPACIDAD (medido con el catálogo real): cada fila de
-- sitios_candidatos pesa ~0.3-0.5 KB; 1.133 marcianos + ~2.090 lunares +
-- 12 terrestres ≈ 1.3 MB. El límite de 500 MB NO se alcanza con filas de
-- resumen; el guardián existe para el día que se suban series temporales
-- u otras tablas al mismo proyecto.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1) Similitud genérica (perfil y fila como JSONB; funciona con cualquier
--    parámetro que exista en parametros_escalas)
-- ---------------------------------------------------------------------------

create or replace function similitud_ponderada(perfil jsonb, datos jsonb)
returns double precision
language plpgsql immutable
as $$
declare
    clave    text;
    peso     double precision;
    objetivo double precision;
    valor    double precision;
    ancho    double precision;
    suma_p   double precision := 0;
    suma_c   double precision := 0;
begin
    if perfil is null or datos is null then
        return null;
    end if;

    for clave, peso, objetivo in
        select k,
               nullif(v->>'peso', '')::double precision,
               (v->>'valor')::double precision
        from jsonb_each(perfil) as t(k, v)
    loop
        if peso is null or peso <= 0 or objetivo is null then
            continue;   -- entrada del perfil sin peso/valor: no compara
        end if;
        valor := nullif(datos->>clave, '')::double precision;
        if valor is null then
            continue;   -- regla de oro: la fuente no dio el dato -> fuera
        end if;
        select (valor_max - valor_min) into ancho
            from parametros_escalas where parametro = clave;
        if ancho is null or ancho = 0 then
            continue;   -- parámetro sin rango definido: fuera
        end if;
        suma_p := suma_p + peso;
        suma_c := suma_c + peso * ((valor - objetivo) / ancho)
                          * ((valor - objetivo) / ancho);
    end loop;

    if suma_p = 0 then
        return null;    -- nada comparable: sin similitud (no se inventa)
    end if;
    if suma_c < 0 then
        suma_c := 0;    -- redondeo flotante: sqrt(negativo) sería NaN
    end if;
    return greatest(0, least(1, 1 - sqrt(suma_c / suma_p)));
end;
$$;

-- ---------------------------------------------------------------------------
-- 2) Desglose por categorías (la "búsqueda flexible" de la Tierra)
-- ---------------------------------------------------------------------------

create or replace function similitudes_por_categoria(perfil jsonb,
                                                     datos jsonb)
returns jsonb
language plpgsql immutable
as $$
declare
    categorias constant jsonb := jsonb_build_object(
        'topografia',   '["elevacion_media_m","pendiente_media_grados",
                          "rugosidad_media_m"]'::jsonb,
        'termico',      '["temperatura_media_k","diferencia_dia_noche_k",
                          "variacion_estacional_k"]'::jsonb,
        'superficie',   '["reflectancia_media"]'::jsonb,
        'iluminacion',  '["energia_solar_media_wm2",
                          "fraccion_diurna"]'::jsonb);
    salida jsonb := '{}'::jsonb;
    cat    text;
    claves jsonb;
    sub    jsonb;
    k      text;
begin
    if perfil is null then
        return null;
    end if;
    for cat, claves in select * from jsonb_each(categorias) loop
        sub := '{}'::jsonb;
        for k in select jsonb_array_elements_text(claves) loop
            if perfil ? k then
                sub := jsonb_set(sub, array[k], perfil->k, true);
            end if;
        end loop;
        salida := salida || jsonb_build_object(
            cat, similitud_ponderada(sub, datos));
    end loop;
    return salida || jsonb_build_object(
        'global', similitud_ponderada(perfil, datos));
end;
$$;

-- ---------------------------------------------------------------------------
-- 3) API por cuerpo: Top N de SOLO ese cuerpo ('luna'|'marte'|'tierra')
-- ---------------------------------------------------------------------------

create or replace function buscar_analogo_cuerpo(parametros jsonb,
                                                 cuerpo text,
                                                 topn int default 1)
returns jsonb
language plpgsql stable
as $$
declare
    perfil   jsonb := coalesce(nullif(parametros->>'perfil', '')::jsonb,
                               parametros);
    cuerpo_n text := lower(cuerpo);
    filas    jsonb;
    n_vistos int;
begin
    if cuerpo_n not in ('tierra', 'luna', 'marte') then
        return jsonb_build_object(
            'error', 'cuerpo desconocido: ' || cuerpo_n,
            'validos', '["tierra","luna","marte"]'::jsonb);
    end if;

    select count(*) into n_vistos
        from sitios_candidatos s where s.cuerpo = cuerpo_n;

    select coalesce(jsonb_agg(
               jsonb_build_object(
                   'sitio_id', d->>'sitio_id',
                   'nombre',   d->>'nombre',
                   'tipo',     d->>'tipo',
                   'cuerpo',   d->>'cuerpo',
                   'lat',      d->>'lat',
                   'lon',      d->>'lon',
                   'similitud', sim,
                   'similitudes', similitudes_por_categoria(perfil, d))
               order by sim desc nulls last),
           '[]'::jsonb)
        into filas
        from (select to_jsonb(s) as d,
                     similitud_ponderada(perfil, to_jsonb(s)) as sim
              from sitios_candidatos s
              where s.cuerpo = cuerpo_n
              order by sim desc nulls last
              limit greatest(1, coalesce(topn, 1))) t;

    return jsonb_build_object(
        'cuerpo', cuerpo_n,
        'perfil_aplicado', perfil,
        'vistos', n_vistos,
        'resultados', filas);
end;
$$;

-- ---------------------------------------------------------------------------
-- 4) La búsqueda completa en UNA llamada:
--    luna_top1 + marte_top1 (APIs propias, individuales) + tierra_top5
--    con desglose por categorías (flexible). Esta es la que usa el
--    cliente por defecto.
-- ---------------------------------------------------------------------------

create or replace function buscar_analogos_v2(parametros jsonb)
returns jsonb
language plpgsql stable
as $$
declare
    perfil jsonb := coalesce(nullif(parametros->>'perfil', '')::jsonb,
                             parametros);
    luna   jsonb;
    marte  jsonb;
    tierra jsonb;
begin
    luna   := buscar_analogo_cuerpo(jsonb_build_object('perfil', perfil),
                                    'luna', 1);
    marte  := buscar_analogo_cuerpo(jsonb_build_object('perfil', perfil),
                                    'marte', 1);
    tierra := buscar_analogo_cuerpo(jsonb_build_object('perfil', perfil),
                                    'tierra', 5);
    return jsonb_build_object(
        'perfil_aplicado', perfil,
        'luna_top1',    luna->'resultados'->0,
        'marte_top1',   marte->'resultados'->0,
        'tierra_top5',  tierra->'resultados',
        'vistos', jsonb_build_object(
            'luna',   luna->'vistos',
            'marte',  marte->'vistos',
            'tierra', tierra->'vistos'));
end;
$$;

-- ---------------------------------------------------------------------------
-- 5) Guardián de almacenamiento (plan Free: 500 MB por proyecto)
-- ---------------------------------------------------------------------------

create or replace function uso_bd() returns jsonb
language sql security definer set search_path = public
as $$
    select jsonb_build_object(
        'bytes_base_datos', pg_database_size(current_database()),
        'bytes_tabla', pg_total_relation_size('sitios_candidatos'),
        'filas', (select count(*) from sitios_candidatos),
        -- techo del plan Free (500 MB en bytes decimales, como lo mide
        -- el panel): informativo; el poblador aplica SU límite configurable
        'limite_plan_bytes', 500000000);
$$;
