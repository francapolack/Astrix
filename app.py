import numpy as np
import pandas as pd
#TEST ARFEA
#over here are the thibngs i test my functions w/
#so tempone,tempmax,tempmin,elev,rugosidad,minerals,atmospheric minerals(LOS MINERALES ENCONTRADOS EN EL PLANETA TENDRIAN QUE SER COLUMNAS CON EL MINERAL Y 1/0)
array1=[0.77,1,2,3.3,4,2,1,1,0]
cleanarray1=[float(i) for i in array1]
df1=pd.DataFrame(cleanarray1)
array1=[0.77,1,2,3.3,4,2,1,1,0]
cleanarray1=[float(i) for i in array1]
df1=pd.DataFrame()
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
#FUNCION DE SIMILTUD EJ
#PARA ESTA FUNCION NECESITO *FILAS DE DATOS*!!! 
def weighted_similarity(raw_array_a,raw_array_b,weights):
    array_a=np.array(raw_array_a)
    array_b=np.array(raw_array_b)
    w=np.array(weights)

    numerator=np.sum(w*array_a*array_b)#top part of the WS ecuation
    denominator=np.sqrt(np.sum(w*(array_a*2)))*np.sqrt(np.sum(w*(array_b*2)))#bottom part
    weigthedsim=numerator/denominator
    if denominator==0:
        print("Division by zero")
        return 0.0
    else:
      return int(weigthedsim*100)/100




