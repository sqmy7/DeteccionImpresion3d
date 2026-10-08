# Progreso de la hora de ausencia (rama `lab-ausente`)

Reglas vigentes: la .22 (trabajo 43) no se toca; la .21 solo lectura; sin `git push`, sin línea de
coautoría en los commits; sin desplegar, sin reiniciar contenedores, sin arrancar `capture`, sin escribir en la base
real (solo SELECT).

## Línea de tiempo

| Hora (Colombia) | Hecho |
|---|---|
| ~15:25 | Rama `lab-ausente` creada desde `main`. Red: SalaSteam_UIS, sin VPN, .22 responde (capa 383/486). **La .21 no responde** (HTTP 000 a 5 y 15 s, ping 100 % perdido, sin entrada ARP) |

## Decisiones tomadas sin ti

1. **.21 sin respuesta:** no se intenta arreglar nada (la regla dice detenerse y avisar; como no puedes
   contestar, se pasa a las tareas sin red y se reintenta cada ~5 min, solo con GET/ping único).
2. El script de búsqueda de cámara se deja escrito y probado contra una impresora simulada, para correrlo en
   cuanto la .21 responda.

## Para Samuel (en orden)

1. Desplegar el backend (reconstruir el contenedor) **cuando la impresión 43 haya terminado**.
2. Reiniciar `capture`.
3. Calibrar la C922 desde la web.
4. Precios reales (filamento y kWh).
5. Revisar la rama `lab-ausente` antes de unirla a `main`.
6. Encender la impresora .21 / confirmar su IP si de verdad es 192.168.10.21.
