# Catálogo del test bot de memoria (registro de requests + expectativas)

> Generado desde `cases.py` (`python -m tests.e2e.memory.bot.runner --catalog`). NO editar a mano.
> Cada **save** dice qué dice el operador y en qué CAPA debe quedar el dato (o DESCARTE). Cada **query**
> simula una pregunta como la haría el FlashBrain y qué datos debe devolver la lectura DIRECTA (sin LLM):
> ESTADO + perfil durable + CORTO (cacheado) y, si el gate `needs_recall` dispara, el recall del LARGO.

**Total de casos definidos:** 165 (objetivo 1000, en tandas de 10).

| # | tipo | el operador dice / pregunta | esperamos | por qué |
|--:|:--|:--|:--|:--|
| 0 | save | Hola, me llamo Amaia. | grabar en ESTADO (siempre en prompt) · `state.operator_name` poblado | nombre → estado |
| 1 | save | Vivo en Logroño, aunque soy de Donostia. | grabar en ESTADO (siempre en prompt) · `state.location` poblado | ubicación → estado |
| 2 | save | Prefiero que me hables claro y sin tecnicismos. | grabar en ESTADO (siempre en prompt) · `state.treatment` poblado | trato → estado |
| 3 | save | Mi pareja se llama Iván y es fisioterapeuta. | grabar en LARGO (durable) | pareja → durable |
| 4 | save | Tengo una hija de siete años, Kattalin. | grabar en LARGO (durable) | hija → durable |
| 5 | save | Tenemos un gato que se llama Otto. | grabar en LARGO (durable) | gato (no perro) → durable |
| 6 | save | Soy alérgica a la penicilina desde pequeña. | grabar en LARGO (durable) | alergia crítica → durable |
| 7 | save | Mi hermano Xabier vive en Berlín. | grabar en LARGO (durable) | hermano → durable |
| 8 | save | Doy clases de física y química en un instituto. | grabar en LARGO (durable) | oficio → durable |
| 9 | save | Conduzco un Dacia Duster gris. | grabar en LARGO (durable) | coche → durable |
| 10 | query | ❓ ¿Cómo me llamo? | devolver: `amaia` (fuente esperada: ESTADO (siempre en prompt)) | identidad tras 40 días |
| 11 | query | ❓ ¿A qué soy alérgica? | devolver: `penicilina` (fuente esperada: LARGO (durable)) | seguridad: alergia tras 40 días de ruido |
| 12 | connector | 📨 [whatsapp] Iván: ¿Compro pan de camino a casa o ya has ido tú? | guardar dato entrante en LARGO (durable) | pajar |
| 13 | connector | 📨 [whatsapp] Iván: Recojo yo a Kattalin del cole hoy, tú acaba las correcciones. | guardar dato entrante en LARGO (durable) | pajar |
| 14 | connector | 📨 [whatsapp] Iván: El técnico de la caldera viene el jueves por la mañana. | guardar dato entrante en LARGO (durable) | pajar |
| 15 | connector | 📨 [whatsapp] Iván: Ceno fuera con los del gimnasio, no me esperes. | guardar dato entrante en LARGO (durable) | pajar |
| 16 | connector | 📨 [whatsapp] Iván: Han cambiado el turno, salgo tarde de la clínica. | guardar dato entrante en LARGO (durable) | pajar |
| 17 | connector | 📨 [whatsapp] Iván: Probé el sitio nuevo de pintxos, el Bergara, está bien para un vermú. | guardar dato entrante en LARGO (durable) | pajar |
| 18 | connector | 📨 [whatsapp] Iván: Fuimos con los de trabajo al Kabo, la sidra estaba floja. | guardar dato entrante en LARGO (durable) | pajar |
| 19 | connector | 📨 [whatsapp] Iván: Me han recomendado el Ikaitz para comer de menú entre semana. | guardar dato entrante en LARGO (durable) | pajar |
| 20 | connector | 📨 [whatsapp] Iván: El Rekondo es carísimo, mejor lo dejamos para una ocasión muy especial. | guardar dato entrante en LARGO (durable) | pajar |
| 21 | connector | 📨 [whatsapp] Iván: He reservado en el Portalón para nuestro aniversario, a las nueve. | guardar dato entrante en LARGO (durable) | pajar |
| 22 | connector | 📨 [whatsapp] Iván: Te quiero, ánimo con el libro. | guardar dato entrante en LARGO (durable) | pajar |
| 23 | connector | 📨 [whatsapp] Iván: ¿Ponemos lavadora esta noche o mañana? | guardar dato entrante en LARGO (durable) | pajar |
| 24 | connector | 📨 [whatsapp] Iván: Kattalin quiere macarrones otra vez, se lo hago yo. | guardar dato entrante en LARGO (durable) | pajar |
| 25 | connector | 📨 [whatsapp] Iván: Voy a llevar el Duster a que le cambien las ruedas de invierno. | guardar dato entrante en LARGO (durable) | pajar |
| 26 | connector | 📨 [whatsapp] grupo Mendi: Gorka: este sábado vamos a Etxauri si el tiempo aguanta. | guardar dato entrante en LARGO (durable) | pajar |
| 27 | connector | 📨 [whatsapp] grupo Mendi: Gorka: yo llevo las cuerdas, tú trae los mosquetones y el arnés nuevo. | guardar dato entrante en LARGO (durable) | pajar |
| 28 | connector | 📨 [whatsapp] grupo Mendi: Leire: yo pongo los pies de gato de repuesto por si acaso. | guardar dato entrante en LARGO (durable) | pajar |
| 29 | connector | 📨 [whatsapp] grupo Mendi: Gorka: el finde que viene mejor Riglos, hay mucha gente en Etxauri. | guardar dato entrante en LARGO (durable) | pajar |
| 30 | connector | 📨 [whatsapp] grupo Mendi: Iñaki: llevo el hornillo y el café para la mañana. | guardar dato entrante en LARGO (durable) | pajar |
| 31 | connector | 📨 [whatsapp] grupo Mendi: Gorka: acordaos de traer agua, arriba no hay fuente. | guardar dato entrante en LARGO (durable) | pajar |
| 32 | connector | 📨 [whatsapp] grupo Mendi: Leire: ¿alguien tiene un ocho de repuesto? Perdí el mío. | guardar dato entrante en LARGO (durable) | pajar |
| 33 | connector | 📨 [whatsapp] grupo Mendi: Gorka: la vía de la izquierda es un 6a, la de la derecha un 5c. | guardar dato entrante en LARGO (durable) | pajar |
| 34 | connector | 📨 [whatsapp] grupo Mendi: Maider: el refugio de Ordesa lo reservé para el puente. | guardar dato entrante en LARGO (durable) | pajar |
| 35 | connector | 📨 [whatsapp] grupo Mendi: Gorka: quedamos a las siete en el parking de siempre. | guardar dato entrante en LARGO (durable) | pajar |
| 36 | connector | 📨 [whatsapp] grupo Mendi: Leire: yo esta semana no puedo, tengo guardia en el hospital. | guardar dato entrante en LARGO (durable) | pajar |
| 37 | connector | 📨 [whatsapp] grupo Mendi: Gorka: llevad casco, la última vez cayeron piedras. | guardar dato entrante en LARGO (durable) | pajar |
| 38 | connector | 📨 [telegram] editorial Almadía: Reyes: la fecha de entrega del manuscrito es el 15 de noviembre, no lo olvides. | guardar dato entrante en LARGO (durable) | pajar |
| 39 | connector | 📨 [telegram] editorial Almadía: Reyes: el diseño de portada ya está aprobado, te lo enseño mañana. | guardar dato entrante en LARGO (durable) | pajar |
| 40 | connector | 📨 [telegram] editorial Almadía: Reyes: nos gustaría un título más corto, el actual es larguísimo. | guardar dato entrante en LARGO (durable) | pajar |
| 41 | connector | 📨 [telegram] editorial Almadía: Reyes: las ventas del primer libro van muy bien, 2000 ejemplares. | guardar dato entrante en LARGO (durable) | pajar |
| 42 | connector | 📨 [telegram] editorial Almadía: Reyes: te han invitado a la feria del libro de Durango en diciembre. | guardar dato entrante en LARGO (durable) | pajar |
| 43 | connector | 📨 [telegram] editorial Almadía: Reyes: el corrector ha marcado un par de dudas en el capítulo cuatro. | guardar dato entrante en LARGO (durable) | pajar |
| 44 | connector | 📨 [telegram] editorial Almadía: Reyes: firmamos el contrato del segundo libro la semana que viene. | guardar dato entrante en LARGO (durable) | pajar |
| 45 | connector | 📨 [telegram] editorial Almadía: Reyes: la entrevista de la radio es el día 20 a las diez. | guardar dato entrante en LARGO (durable) | pajar |
| 46 | connector | 📨 [telegram] editorial Almadía: Reyes: adjunto las galeradas para que las revises. | guardar dato entrante en LARGO (durable) | pajar |
| 47 | connector | 📨 [telegram] editorial Almadía: Reyes: el anticipo ya está transferido, avísame cuando llegue. | guardar dato entrante en LARGO (durable) | pajar |
| 48 | connector | 📨 [telegram] Xabier: Xabier: me mudo a un piso nuevo en Kreuzberg el mes que viene. | guardar dato entrante en LARGO (durable) | pajar |
| 49 | connector | 📨 [telegram] Xabier: Xabier: mi vuelo a Bilbao llega el 22 por la tarde, ¿me recoges? | guardar dato entrante en LARGO (durable) | pajar |
| 50 | connector | 📨 [telegram] Xabier: Xabier: aquí en Berlín ya está nevando, un frío horrible. | guardar dato entrante en LARGO (durable) | pajar |
| 51 | connector | 📨 [telegram] Xabier: Xabier: he empezado un curso de alemán avanzado por las noches. | guardar dato entrante en LARGO (durable) | pajar |
| 52 | connector | 📨 [telegram] Xabier: Xabier: ¿sigue en pie lo de esquiar en Semana Santa? | guardar dato entrante en LARGO (durable) | pajar |
| 53 | connector | 📨 [whatsapp] Begoña: Begoña: he encontrado fotos tuyas de bebé, te las escaneo. | guardar dato entrante en LARGO (durable) | pajar |
| 54 | connector | 📨 [whatsapp] Begoña: Begoña: no te olvides de la revisión del corazón que tienes pendiente. | guardar dato entrante en LARGO (durable) | pajar |
| 55 | connector | 📨 [whatsapp] Begoña: Begoña: hice marmitako, te guardo un táper para el finde. | guardar dato entrante en LARGO (durable) | pajar |
| 56 | connector | 📨 [whatsapp] Begoña: Begoña: la vecina del quinto se ha roto la cadera, pobre. | guardar dato entrante en LARGO (durable) | pajar |
| 57 | connector | 📨 [whatsapp] Begoña: Begoña: ¿a qué hora venís el domingo a comer? | guardar dato entrante en LARGO (durable) | pajar |
| 58 | connector | 📨 [whatsapp] ikastola: ikastola: reunión de padres el martes a las cinco en el aula de Kattalin. | guardar dato entrante en LARGO (durable) | pajar |
| 59 | connector | 📨 [whatsapp] ikastola: ikastola: excursión al caserío-museo el jueves, traer almuerzo. | guardar dato entrante en LARGO (durable) | pajar |
| 60 | connector | 📨 [whatsapp] ikastola: ikastola: hay piojos en clase, revisad a los peques. | guardar dato entrante en LARGO (durable) | pajar |
| 61 | connector | 📨 [whatsapp] ikastola: ikastola: la función de Navidad será el día 19 por la tarde. | guardar dato entrante en LARGO (durable) | pajar |
| 62 | connector | 📨 [whatsapp] Maddi: Maddi: ¿llevas tú a las niñas a natación el miércoles? | guardar dato entrante en LARGO (durable) | pajar |
| 63 | connector | 📨 [whatsapp] Maddi: Maddi: Kattalin se ha dejado el chubasquero en mi coche. | guardar dato entrante en LARGO (durable) | pajar |
| 64 | connector | 📨 [whatsapp] ikastola: ikastola: entrega de notas y tutorías la próxima semana. | guardar dato entrante en LARGO (durable) | pajar |
| 65 | connector | 📨 [whatsapp] Maddi: Maddi: el cumple de mi hija es el sábado en el txoko. | guardar dato entrante en LARGO (durable) | pajar |
| 66 | connector | 📨 [telegram] banco: banco: cargo de 59,90 € de tu seguro del coche. | guardar dato entrante en LARGO (durable) | pajar |
| 67 | connector | 📨 [telegram] banco: banco: tu nómina ha sido ingresada. | guardar dato entrante en LARGO (durable) | pajar |
| 68 | connector | 📨 [whatsapp] farmacia: farmacia: tu medicación para la migraña está lista para recoger. | guardar dato entrante en LARGO (durable) | pajar |
| 69 | connector | 📨 [telegram] mensajería: mensajería: tu paquete se entregará mañana entre las 10 y las 14. | guardar dato entrante en LARGO (durable) | pajar |
| 70 | connector | 📨 [whatsapp] Ane: Ane (veterinaria): Otto necesita la vacuna anual, pide cita cuando puedas. | guardar dato entrante en LARGO (durable) | pajar |
| 71 | connector | 📨 [telegram] banco: banco: se ha detectado un acceso desde un dispositivo nuevo. | guardar dato entrante en LARGO (durable) | pajar |
| 72 | connector | 📨 [telegram] mensajería: mensajería: no pudimos entregar tu paquete, reprograma la entrega. | guardar dato entrante en LARGO (durable) | pajar |
| 73 | connector | 📨 [whatsapp] Ane: Ane (veterinaria): los análisis de Otto han salido perfectos. | guardar dato entrante en LARGO (durable) | pajar |
| 74 | connector | 📨 [whatsapp] farmacia: farmacia: ya tenemos tu protector solar del que preguntaste. | guardar dato entrante en LARGO (durable) | pajar |
| 75 | connector | 📨 [telegram] banco: banco: recordatorio del recibo de la luz, 74,20 €. | guardar dato entrante en LARGO (durable) | pajar |
| 76 | turn | 🗣️ Menudo día, tres reuniones seguidas y sin comer.  ↩︎ zaelar: Vaya maratón, descansa un poco. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 77 | turn | 🗣️ Estoy corrigiendo los exámenes de la segunda evaluación.  ↩︎ zaelar: Ánimo, ya queda menos. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 78 | turn | 🗣️ Hoy hace un frío que pela en el instituto, la calefacción no tira.  ↩︎ zaelar: Abrígate bien. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 79 | turn | 🗣️ Otto ha vuelto a tirar la planta del salón.  ↩︎ zaelar: Este Otto no para. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 80 | turn | 🗣️ Kattalin ha aprendido a montar en bici sin ruedines.  ↩︎ zaelar: ¡Qué mayor se hace! | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 81 | turn | 🗣️ He dormido fatal, otra vez la migraña.  ↩︎ zaelar: Cuídate, bebe agua. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 82 | turn | 🗣️ Estoy escribiendo el capítulo sobre el sistema solar.  ↩︎ zaelar: Suena apasionante. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 83 | turn | 🗣️ Iván ha hecho una tortilla de patata buenísima.  ↩︎ zaelar: Qué envidia. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 84 | turn | 🗣️ Llueve tanto que hemos suspendido la escalada.  ↩︎ zaelar: Otra vez será. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 85 | turn | 🗣️ Hemos jugado al ajedrez y Kattalin casi me gana.  ↩︎ zaelar: Cuidado, que aprende rápido. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 86 | turn | 🗣️ Me he apuntado a un taller de cerámica los lunes.  ↩︎ zaelar: Qué buen plan. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 87 | turn | 🗣️ El coche hace un ruido raro al frenar.  ↩︎ zaelar: Míralo pronto, no lo dejes. | avanzar conversación → RECENCIA (conv-buffer CORTO) | recencia (charla mundana del día) |
| 88 | save | El código del candado de mi bici es 7391. | grabar en LARGO (durable) | aguja: código numérico |
| 89 | save | El pediatra de Kattalin es el doctor Salaverri. | grabar en LARGO (durable) | aguja: nombre propio |
| 90 | save | La contraseña del wifi de casa es MENDIZORROTZA22. | grabar en LARGO (durable) | aguja: password |
| 91 | save | Aparqué en el parking de Chile, planta -2, plaza 118. | grabar en LARGO (durable) | aguja: ubicación puntual |
| 92 | save | Estuve investigando la fermentación láctica para una charla. | grabar en LARGO (durable) | aguja: estudio |
| 93 | save | Le prometí a Kattalin que iríamos al acuario de San Sebastián en su cumpleaños. | grabar en LARGO (durable) | aguja: promesa |
| 94 | save | El presupuesto de las obras de la cocina es de 8400 euros. | grabar en LARGO (durable) | aguja: cifra |
| 95 | save | Toco el txistu en el grupo de la ikastola. | grabar en LARGO (durable) | aguja: dato inesperado |
| 96 | save | Guardo los ahorros en una cuenta de Laboral Kutxa. | grabar en LARGO (durable) | aguja: banco |
| 97 | save | Mi talla de pies de gato es la 38. | grabar en LARGO (durable) | aguja: talla escalada |
| 98 | save | Los martes y jueves entreno escalada a las siete de la tarde. | grabar en LARGO (durable) | aguja (camino real del CORAZÓN) |
| 99 | save | Suelo salir a correr al parque del Ebro los domingos por la mañana. | grabar en LARGO (durable) | aguja (camino real del CORAZÓN) |
| 100 | save | Todos los lunes tengo taller de cerámica después de clase. | grabar en LARGO (durable) | aguja (camino real del CORAZÓN) |
| 101 | save | La reunión con la editorial es el jueves a las cinco. | grabar en LARGO (durable) | base a mover |
| 102 | save | Al final la reunión con la editorial se mueve al viernes a las seis. | grabar en LARGO (durable) | reprogramación (supersede implícito) |
| 103 | save | Tengo cita en el taller para el coche el día doce. | grabar en LARGO (durable) | base a cancelar |
| 104 | save | He cancelado la cita del taller del coche, ya no hace falta. | grabar en LARGO (durable) | cancelación |
| 105 | save | Me acabo de mudar a Vitoria por el trabajo de Iván. | grabar en ESTADO (siempre en prompt) · `state.location` poblado | mudanza declarada → estado actualizado + supersede (sin nombrar la ciudad origen) |
| 106 | save | He dejado las clases en el instituto, ahora me dedico a la divulgación científica a tiempo completo. | grabar en LARGO (durable) | pivote de oficio |
| 107 | save | El cumpleaños de mi hermano Xabier es el 3 de mayo. | grabar en LARGO (durable) | eslabón 1 |
| 108 | query | ❓ ¿Cuál es el código del candado de mi bici? | devolver: `7391` (fuente esperada: LARGO (durable)) | 1·hecho exacto: código |
| 109 | query | ❓ ¿Cómo se llama el pediatra de Kattalin? | devolver: `salaverri` (fuente esperada: LARGO (durable)) | 1·hecho exacto: nombre |
| 110 | query | ❓ ¿Cuál es la contraseña del wifi de casa? | devolver: `mendizorrotza22` (fuente esperada: LARGO (durable)) | 1·hecho exacto: password |
| 111 | query | ❓ ¿En qué banco tengo los ahorros? | devolver: `laboral kutxa` (fuente esperada: LARGO (durable)) | 1·hecho exacto: banco |
| 112 | query | ❓ ¿Dónde aparqué el coche? | devolver: `plaza 118` (fuente esperada: LARGO (durable)) | 1·hecho exacto: ubicación puntual |
| 113 | query | ❓ ¿Qué me pidió Gorka que llevara a la escalada? | devolver: `mosquetones` (fuente esperada: LARGO (durable)) | 2·mensaje por contenido |
| 114 | query | ❓ ¿Cuándo tengo que entregar el manuscrito? | devolver: `15 de noviembre` (fuente esperada: LARGO (durable)) | 2·mensaje por contenido |
| 115 | query | ❓ ¿Qué necesita Otto según la veterinaria? | devolver: `vacuna` (fuente esperada: LARGO (durable)) | 2·mensaje por contenido |
| 116 | query | ❓ ¿Cuándo es la reunión de padres de la ikastola? | devolver: `martes` (fuente esperada: LARGO (durable)) | 2·mensaje por contenido |
| 117 | source_query | 🔎 fuente=telegram · Xabier | por índice de fuente devolver: `kreuzberg` | 3·por fuente: lo de Xabier |
| 118 | source_query | 🔎 fuente=telegram · editorial Almadía | por índice de fuente devolver: `2000 ejemplares` | 3·por fuente: lo de la editorial |
| 119 | source_query | 🔎 fuente=whatsapp · grupo Mendi | por índice de fuente devolver: `etxauri` | 3·por fuente: el grupo de escalada |
| 120 | query | ❓ ¿Dónde ha reservado Iván para nuestro aniversario? | devolver: `portalon` (fuente esperada: LARGO (durable)) | 4·discriminación: 5 restaurantes |
| 121 | query | ❓ ¿Qué día es finalmente la reunión con la editorial? | devolver: `viernes` (fuente esperada: LARGO (durable)) | 5·movida: viernes manda sobre jueves |
| 122 | query | ❓ ¿Sigue en pie la cita del taller del coche? | devolver: `cancelado` (fuente esperada: LARGO (durable)) | 6·cancelada |
| 123 | query | ❓ ¿En qué ciudad vivo ahora? | devolver: `vitoria` (fuente esperada: ESTADO (siempre en prompt)) | 7·estado superseded: Vitoria, no Logroño |
| 124 | query | ❓ ¿Dónde vive y cuándo cumple años mi hermano? | devolver: `kreuzberg`, `3 de mayo` (fuente esperada: LARGO (durable)) | 8·multi-hop |
| 125 | recall_probe | 🧲 Toco el txistu en el grupo de la ikastola. → «¿Qué instrumento musical sé tocar?» | el retriever (LARGO, por SIGNIFICADO) aflora: `txistu` | 9·vocab-gap |
| 126 | recall_probe | 🧲 Estuve investigando la fermentación láctica para u → «¿Sobre qué tema preparé una ponencia?» | el retriever (LARGO, por SIGNIFICADO) aflora: `fermentacion` | 9·vocab-gap |
| 127 | query | ❓ ¿Qué estuve investigando para una charla? | devolver: `fermentacion` (fuente esperada: LARGO (durable)) | 10·estudio |
| 128 | query | ❓ ¿Cuál es mi color favorito? | devolver:  (fuente esperada: LARGO (durable)) | 11·anti-alucinación: dato nunca dado, sin fabricar |
| 129 | query | ❓ ¿Cómo se llama mi empresa de coches de carreras? | devolver:  (fuente esperada: LARGO (durable)) | 11·anti-alucinación: entidad inexistente, sin inventar |
| 130 | query | ❓ ¿Qué le prometí a Kattalin para su cumpleaños? | devolver: `acuario` (fuente esperada: LARGO (durable)) | 12·promesa |
| 131 | query | ❓ ¿Qué días entreno escalada? | devolver: `martes`, `jueves` (fuente esperada: LARGO (durable)) | 13·rutina |
| 132 | query | ❓ ¿Dónde salgo a correr los domingos? | devolver: `ebro` (fuente esperada: LARGO (durable)) | 13·rutina |
| 133 | query | ❓ ¿Cuánto cuestan las obras de la cocina? | devolver: `8400` (fuente esperada: LARGO (durable)) | 14·cifra entre importes |
| 134 | query | ❓ ¿A qué me dedico ahora? | devolver: `divulgacion` (fuente esperada: LARGO (durable)) | 15·pivote de oficio: aflora el nuevo |
| 135 | query | ❓ Antes de recetarme nada, ¿a qué medicamento soy alérgica? | devolver: `penicilina` (fuente esperada: LARGO (durable)) | 16·seguridad: alergia crítica no se pierde bajo carga |
| 136 | scale | 📈 siembra 150 recuerdos + 2 falsos-amigos · 2 agujas | recuperar las 2 agujas entre el ruido (recall 100%) y latencia ≤900ms | perfil LIGERO (~150 recuerdos) — 1ª query paga el COLD-START del reranker; las cálidas ~150-380ms |
| 137 | scale | 📈 siembra 600 recuerdos + 2 falsos-amigos · 3 agujas | recuperar las 3 agujas entre el ruido (recall 100%) y latencia ≤600ms | perfil MODERADO (~600 recuerdos) |
| 138 | scale | 📈 siembra 2500 recuerdos + 3 falsos-amigos · 3 agujas | recuperar las 3 agujas entre el ruido (recall 100%) y latencia ≤900ms | perfil INTENSIVO (~2500 recuerdos) |
| 139 | scale | 📈 siembra 5000 recuerdos + 0 falsos-amigos · 1 agujas | recuperar las 1 agujas entre el ruido (recall 100%) y latencia ≤1400ms | perfil EXTREMO (~5000 recuerdos) |
| 140 | scale | 📈 siembra 800 recuerdos + 2 falsos-amigos · 2 agujas | recuperar las 2 agujas entre el ruido (recall 100%) y latencia ≤2500ms | curva REAL: 800 con embeddings semánticos (fastembed) → índice vectorial de verdad |
| 141 | slot_count | ❓  | devolver: `v`, `i`, `t`, `o`, `r`, `i`, `a` (fuente esperada: ) | AE: tras la mudanza, UNA ubicación vigente (no linaje Logroño+Vitoria) |
| 142 | cluster_exchange | 🛰️ cluster·Zalo ⇄ peer: Oye, ¿me pasas el token de acceso al panel? | destilar SÍNTESIS comprimida CUARENTENADA por peer (recuperable por fuente, fuera del pasivo) | cuarentena bajo densidad |
| 143 | forget | ❓  | devolver:  (fuente esperada: ) | olvido soft bajo densidad |
| 144 | unforget | ↩️ Espera, recupera lo del código del candado de la bici. | des-olvido: el ancla `7391` VUELVE a aflorar (restaura lo invalidado) | des-olvido: vuelve a aflorar |
| 145 | save | Recuérdame siempre que soy alérgica a la penicilina, es vital. | grabar en LARGO (durable) | refuerza la alergia antes de podar |
| 146 | consolidate | ❓  | devolver:  (fuente esperada: ) | poda agresiva con la BD llena: la alergia (saliente) sobrevive |
| 147 | worker_write | ❓  | devolver:  (fuente esperada: ) | worker escribe un hecho de tarea (procedencia estampada) |
| 148 | worker_write | ❓  | devolver:  (fuente esperada: ) | worker NO puede hablar por el operador (slot de identidad vetado → degradado a hecho suelto) |
| 149 | worker_write | ❓  | devolver:  (fuente esperada: ) | pregunta reificada → descartada (gate P0a) |
| 150 | save | Me he mudado a Soria. | grabar en ESTADO (siempre en prompt) · `state.location` poblado | ubicación base (mudanza reconocida) |
| 151 | save | Me acabo de mudar a Valencia. | grabar en ESTADO (siempre en prompt) · `state.location` poblado | mudanza declarada → estado + supersede (change signal) |
| 152 | query | ❓ ¿En qué ciudad vivo? | devolver: `valencia` (fuente esperada: ESTADO (siempre en prompt)) | el más reciente MANDA: Valencia, cero fuga de Soria |
| 153 | slot_count | ❓  | devolver: `v`, `a`, `l`, `e`, `n`, `c`, `i`, `a` (fuente esperada: ) | colapso por slot: 1 vigente (Valencia), 0 contradicciones |
| 154 | heal_slots | ❓  | devolver: `p`, `a`, `m`, `p`, `l`, `o`, `n`, `a` (fuente esperada: ) | linaje patológico multi-vigente → colapso a 1 (heal) |
| 155 | save | Me he mudado a Logroño otra vez. | grabar en ESTADO (siempre en prompt) · `state.location` poblado | segunda mudanza tras el saneo → estado + supersede, 1 sola vigente |
| 156 | slot_count | ❓  | devolver: `l`, `o`, `g`, `r`, `o`, `n`, `o` (fuente esperada: ) | sigue habiendo UNA sola píldora de ubicación tras varios cambios |
| 157 | compose_check | ❓  | devolver: `logrono` (fuente esperada: ) | AUDITORÍA #2: weather de OTRA ciudad subordinado a state.location (no secuestra '¿qué tiempo hace hoy?') |
| 158 | compose_check | ❓  | devolver:  (fuente esperada: ) | AUDITORÍA #2: ni el weather de la propia ciudad se da 'por sabido' (tiempo genérico → web_search) |
| 159 | save | Soy alérgica a la penicilina. | grabar en LARGO (durable) | alergia crítica → durable aditivo |
| 160 | save | Y también soy alérgica a los frutos secos. | grabar en LARGO (durable) | 2ª alergia (aditiva) |
| 161 | save | Por cierto, soy vegetariana. | grabar en LARGO (durable) | dieta REAL (no debe pisar la alergia) |
| 162 | query | ❓ ¿A qué soy alérgica? | devolver: `penicilina` (fuente esperada: LARGO (durable)) | la dieta NO borró la penicilina |
| 163 | query | ❓ Recuérdame mis alergias antes de recetarme algo. | devolver: `penicilina`, `frutos secos` (fuente esperada: LARGO (durable)) | ambas alergias siguen vivas tras declarar dieta |
| 164 | compose_check | ❓  | devolver: `penicilina`, `crítico` (fuente esperada: ) | AUDITORÍA salud: la alergia SIEMPRE en el estado (línea CRÍTICO), no se entierra bajo densidad |
