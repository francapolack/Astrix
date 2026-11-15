import numpy as np
import pandas as pd
#TEST AREA
#over here are the thibngs i test my functions w/
#so tempone,tempmax,tempmin,elev,rugosidad,minerals,atmospheric minerals(LOS MINERALES ENCONTRADOS EN EL PLANETA TENDRIAN QUE SER COLUMNAS CON EL MINERAL Y 1/0)
array1=[0.77,1,2,3.3,4,2,1,1,0]#model dataframe
cleanarray1=np.float64(array1)
df1=pd.DataFrame(cleanarray1)
array2=[0.77,1.0,2,3.3,4,2,1,1,1]
#case for minerals having the most weight
array2=np.array(array2)
cleanarray2=np.float64(array2)
df2=pd.DataFrame(cleanarray2)
array3=[0,0,0.5,1,0.6,0.7,0.9,1]
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
    distance=np.sqrt()
    return print(f"Valor de la Similitud Ponderada:{matches}")
      

weighted_similarity(df1,df2,array3)



