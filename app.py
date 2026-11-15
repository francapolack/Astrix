import numpy as np
import pandas as pd
#TEST AREA
#over here are the thibngs i test my functions w/
#so tempone,tempmax,tempmin,elev,rugosidad,minerals,atmospheric minerals(LOS MINERALES ENCONTRADOS EN EL PLANETA TENDRIAN QUE SER COLUMNAS CON EL MINERAL Y 1/0)
array1=[0.77,1,2,3.3,4,2,1,1,0]#model dataframe
cleanarray1=np.float64(array1)
df1=pd.DataFrame(cleanarray1)
array2=[[0.77,1.0,2,3.3,4,2,1,1,1],[0.67,6,1,0.0,2,3,1,1,0],[0,0,0,1,2,3,0,0,1],[0.77,1,1,2,0,0,0,0,0]]
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
#PARA ESTA FUNCION NECESITO *FILAS DE DATOS*!!! 
def weighted_similarity(raw_array_a,raw_array_b,weights):
    array_a=np.array(raw_array_a)
    array_b=np.array(raw_array_b)
    w=np.array(weights)
    for i in range(0,(len(array_b))):
       for j in range(0,(len(array_b[0]))):
         numerator=np.sum(w*array_a*array_b[i][j])#top part of the WS ecuation
         denominator=np.sqrt(np.sum(w*(array_a*2)))*np.sqrt(np.sum(w*(array_b[i][j]*2)))#bottom part
         weigthedsim=numerator/denominator
         if denominator==0:
            print("Division by zero")
            return 0.0
         else:
            matches=int(weigthedsim*100)/100
            print(f"\n{matches}")

weighted_similarity(df1,df2,array3)



