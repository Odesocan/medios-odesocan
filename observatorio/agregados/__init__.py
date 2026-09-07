"""
Agregados precalculados.

    wordcloud.py  el agregado textual de la nube de palabras

Este subpaquete es DELIBERADAMENTE independiente del resto: no importa nada de
`observatorio`, se configura solo por variables de entorno y habla con Supabase
por su cliente REST. Su workflow instala únicamente `requirements/wordcloud.txt`
(el paquete `supabase` y nada más), así que cualquier import hacia otra capa
rompería ese pipeline.
"""
