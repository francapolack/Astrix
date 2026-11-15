import numpy as np
#CLASIFICACION DE CATEGORIAS
#all list of categories
atmospherecats=["oksoisortofneedtheapisresult4this"]
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




