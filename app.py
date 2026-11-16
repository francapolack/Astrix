import numpy as np
import pandas as pd
#TEST AREA
#over here are the thibngs i test my functions w/
#so tempone,tempmax,tempmin,elev,rugosidad,minerals,atmospheric minerals(LOS MINERALES ENCONTRADOS EN EL PLANETA TENDRIAN QUE SER COLUMNAS CON EL MINERAL Y 1/0)
array1=[0.77,1,2,3.3,4,2,1,1,0]#model dataframe
cleanarray1=np.float64(array1)
df1=pd.DataFrame(cleanarray1)
array2=[
        [0.77,1,2,3.3,4,2,1,1,0],
        [0,1,2,3.3,4,2,0,0,0],
        [0,1,2,3.3,4,2,0,0,0],
        [0,1,2,3.3,4,2,0,0,0],
        [0,1,2,3.3,4,2,0,0,0]
      ]
#case for minerals having the most weight
df2=pd.DataFrame(array2)
print(df2)
array2=np.array(array2)
cleanarray2=np.float64(array2)
array3=[0,1,0.5,0,0,0.5,1,1,0]
#CLASIFICACION DE CATEGORIAS
#all list of categories
atmospherecats=["temperature"]
geocats=[""]
chemcats=[""]
categories={
   "Atmospheric": atmospherecats,
   "Geologic": geocats,
   "Chemical": chemcats
}
# medium_list=[i for i in range(0,0,0.1)]#im not writing all these nuimbers lets be real
category_weights={
   "a lot":1,#importa mucho
   "not much":0#no importa 
}

#FUNCION DE SIMILTUD EJ

def weighted_similarity(raw_array_a,raw_array_b,weights):
    all_matches=[]
    index_matches=[]
    array_a=np.array(raw_array_a)
    array_b=np.array(raw_array_b)
    w=np.array(weights)
    first_part=(array_b-array_a)**2
    distance=np.sqrt(np.sum(w*first_part,axis=-1))
    matches=1/(1+distance)
    max_index=None
    max_match=max(matches)
    max_value=array_b[0][0]
    for i in range(0,len(array_b)):
        for j in range(0,len(array_b[0])):
            if array_b[i][j]>max_value:
                max_value=array_b[i][j]
                max_index=i
    return print(f"Valor de la mayor Similitud Ponderada:{max_match} Index: {max_index}")
weighted_similarity(cleanarray1,cleanarray2,array3)



