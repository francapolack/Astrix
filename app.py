import numpy as np
import pandas as pd
#TEST AREA
#over here are the thibngs i test my functions w/
#so tempone,tempmax,tempmin,elev,rugosidad,minerals,atmospheric minerals(LOS MINERALES ENCONTRADOS EN EL PLANETA TENDRIAN QUE SER COLUMNAS CON EL MINERAL Y 1/0)
array1=[0.77,1,2,3.3,4,2,1,1,0]#model dataframe
cleanarray1=[float(i) for i in array1]
df1=pd.DataFrame(cleanarray1)
array2=[[0.77,1,2,3.3,4,2,1,1,1],[0.67,6,1,0.0,2,3,1,1,0],[0,0,0,1,2,3,0,0,1],[0.77,1,1,2,0,0,0,0,0]]
#case for minerals having the most weight
cleanarray2=[float(i) for i in array2]
df2=pd.DataFrame(cleanarray2)
array3=[0,0,0,1,2,3,0,0,1]#case for geologicals having the most weight
cleanarray3=[float(i) for i in array3]
df3=pd.DataFrame(cleanarray3)
array4=[0.77,1,1,2,0,0,0,0,1]#case for atmosphere having the most weight
cleanarray4=[float(i) for i in array4]
df4=pd.DataFrame(cleanarray4)
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
medium_list=[i for i in range(0,0,0.1)]#im not writing all these nuimbers lets be real
category_weights={
   "a lot":1,#importa mucho
   "medium":medium_list,#importa un tanto
   "not much":0#no importa 
}
#FUNCION DE SIMILTUD EJ
#PARA ESTA FUNCION NECESITO *FILAS DE DATOS*!!! 
def weighted_similarity(raw_array_a,raw_array_b):
    array_a=np.array(raw_array_a)
    array_b=np.array(raw_array_b)
    weights_input=str(input("How important is this category to you?:"))
    if weights_input=="a lot":#esto es un click del mouse?
       pass#im wortking on this ignore it
    w=np.array(weights)

    numerator=np.sum(w*array_a*array_b)#top part of the WS ecuation
    denominator=np.sqrt(np.sum(w*(array_a*2)))*np.sqrt(np.sum(w*(array_b*2)))#bottom part
    weigthedsim=numerator/denominator
    if denominator==0:
        print("Division by zero")
        return 0.0
    else:
      return int(weigthedsim*100)/100
    
def sir_compares_a_lot(a1,a2):#array number one which should be the array generated from the user analog preferences
    #the other is a array with all the lists
    matches=np.isin(a1,a2)
    return matches
sir_compares_a_lot()



