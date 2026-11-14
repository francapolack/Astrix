import numpy as np
#FUNCION DE SIMILTUD EJ
a=[1,2,3]
b=[3,2,1]
we=[1,0.0,0.5]
def weighted_similarity(raw_array_a,raw_array_b,weights):
    array_a=np.array(raw_array_a)
    array_b=np.array(raw_array_b)
    w=np.array(weights)

    numerator=np.sum(w*array_a*array_b)#top part of the WS ecuation
    denominator=np.sqrt(np.sum(w*(array_a*2)))*np.sqrt(np.sum(w*(array_b*2)))#bottom part
    weigthed_sim=numerator/denominator
    if weigthed_sim

print(weighted_similarity(a,b,we))



