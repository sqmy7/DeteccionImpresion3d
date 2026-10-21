# Flujogramas estilo Flowgorithm — Semana 7 y 8

Convención de símbolos:

```
([ Inicio / Fin ])     óvalo: empieza o termina
[ proceso ]            rectángulo: asignación o cálculo
[/ entrada/salida /]   paralelogramo: input / print / return
< ¿condición? >        rombo: decisión (Sí / No)
◄──┘                   flecha que regresa: el ciclo vuelve a preguntar
```

---

# CÓMO FUNCIONA `sum(fila)` (aparece en casi todos los ejercicios)

`sum(fila)` es un ciclo escondido que acumula los elementos de una lista.

```
([ Inicio sum(fila) ])
          │
   [ total = 0 ]
          │
   ┌─►< ¿quedan elementos en fila? >──No──►[/ devolver total /]──►([ Fin ])
   │              │ Sí
   │      [ x = siguiente elemento ]
   │              │
   │      [ total = total + x ]
   │              │
   └──────────────┘
```

Traza con `fila = [4, 3, 2]`:

| Vuelta | x | total antes | total después |
|---|---|---|---|
| (inicio) | — | — | 0 |
| 1 | 4 | 0 | 4 |
| 2 | 3 | 4 | 7 |
| 3 | 2 | 7 | 9 |
| fin | — | — | **devuelve 9** |

Equivale a:

```python
total = 0
for x in fila:
    total = total + x
```

---

# SEMANA 7 — MATRICES

Recordatorio: `M[i][j]` = fila `i`, columna `j`. `len(M)` = filas, `len(M[0])` = columnas.

```
M = [[4,3,2],
     [1,5,9]]
        j=0 j=1 j=2
  i=0 [  4   3   2 ]
  i=1 [  1   5   9 ]
```

## B1. `promedio_filas(M)`

```
([ Inicio promedio_filas(M) ])
              │
      [ resultado = [] ]
              │
   ┌─►< ¿quedan filas en M? >──No──►[/ return resultado /]──►([ Fin ])
   │              │ Sí
   │      [ fila = siguiente fila ]
   │              │
   │      [ s = sum(fila) ]          ← ciclo de arriba
   │              │
   │      [ n = len(fila) ]
   │              │
   │      [ prom = s / n ]
   │              │
   │      [ resultado.append(prom) ]
   │              │
   └──────────────┘
```

Traza con `M = [[4,3,2],[1,5,9]]`:

| fila | sum(fila) | len(fila) | prom | resultado |
|---|---|---|---|---|
| [4,3,2] | 4+3+2 = 9 | 3 | 3.0 | [3.0] |
| [1,5,9] | 1+5+9 = 15 | 3 | 5.0 | [3.0, 5.0] |

Salida: `[3.0, 5.0]`

## B2. Máximo y su posición

```
([ Inicio ])
      │
[ maximo = M[0][0] ]
[ pos = (0,0) ]
      │
[ i = 0 ]
      │
┌─►< ¿i < len(M)? >──No──►[/ print maximo, pos /]──►([ Fin ])
│          │ Sí
│     [ j = 0 ]
│          │
│   ┌─►< ¿j < len(M[i])? >──No──┐
│   │        │ Sí               │
│   │  < ¿M[i][j] > maximo? >   │
│   │     │Sí        │No       │
│   │ [ maximo = M[i][j] ]      │
│   │ [ pos = (i,j) ]           │
│   │     │          │          │
│   │     └────┬─────┘          │
│   │   [ j = j + 1 ]           │
│   └──────────┘                │
│                         [ i = i + 1 ]
└───────────────────────────────┘
```

Traza con `M = [[4,3,2],[1,9,5],[7,8,6]]`:

| i,j | M[i][j] | ¿> maximo? | maximo | pos |
|---|---|---|---|---|
| inicio | — | — | 4 | (0,0) |
| 0,0 | 4 | No | 4 | (0,0) |
| 0,1 | 3 | No | 4 | (0,0) |
| 0,2 | 2 | No | 4 | (0,0) |
| 1,0 | 1 | No | 4 | (0,0) |
| 1,1 | 9 | **Sí** | 9 | (1,1) |
| 1,2 | 5 | No | 9 | (1,1) |
| 2,0 | 7 | No | 9 | (1,1) |
| 2,1 | 8 | No | 9 | (1,1) |
| 2,2 | 6 | No | 9 | (1,1) |

Salida: `Maximo: 9 en la posicion (1, 1)`

## B3. Crear e imprimir matriz

```
([ Inicio ])
      │
[/ leer f /]
[/ leer c /]
      │
  [ M = [] ]
      │
  [ i = 0 ]
      │
┌─►< ¿i < f? >──No──┐
│       │ Sí        │
│  [ fila = [] ]    │
│  [ j = 0 ]        │
│       │           │
│ ┌─►< ¿j < c? >─No─┤ (sale a guardar la fila)
│ │      │ Sí       │
│ │ [/ leer valor /]│
│ │ [ fila.append(valor) ]
│ │ [ j = j + 1 ]   │
│ └──────┘          │
│  [ M.append(fila) ]
│  [ i = i + 1 ]    │
└───────────────────┘
      │ (matriz llena)
      ▼
┌─►< ¿quedan filas en M? >──No──►([ Fin ])
│          │ Sí
│   ┌─►< ¿quedan x en la fila? >──No──┐
│   │        │ Sí                     │
│   │  [/ print x con ancho 5 /]      │
│   └────────┘                        │
│                          [/ salto de línea /]
└─────────────────────────────────────┘
```

Idea clave: el ciclo exterior crea **filas**, el interior crea los **elementos** de cada fila. `f"{x:5}"` reserva 5 espacios para que las columnas queden alineadas.

## B4. Sumas por fila y por columna

Parte 1 — por fila (usa `sum`):

```
([ Inicio ])
      │
┌─►< ¿quedan filas (i)? >──No──┐
│         │ Sí                 │
│  [/ print i, sum(M[i]) /]    │
└─────────┘                    │
                               ▼
                        (sigue parte 2)
```

Parte 2 — por columna (hay que fijar `j` y recorrer las filas `i`):

```
[ j = 0 ]
    │
┌─►< ¿j < len(M[0])? >──No──►([ Fin ])
│          │ Sí
│    [ suma = 0 ]
│    [ i = 0 ]
│          │
│  ┌─►< ¿i < len(M)? >──No──┐
│  │        │ Sí            │
│  │  [ suma = suma + M[i][j] ]
│  │  [ i = i + 1 ]         │
│  └────────┘               │
│                  [/ print j, suma /]
│                  [ j = j + 1 ]
└────────────────────────────┘
```

Traza con `M = [[4,3,2],[1,5,9],[7,8,6]]`:

Por fila:

| i | fila | sum |
|---|---|---|
| 0 | [4,3,2] | 9 |
| 1 | [1,5,9] | 15 |
| 2 | [7,8,6] | 21 |

Por columna (se recorre hacia abajo):

| j | M[0][j] + M[1][j] + M[2][j] | suma |
|---|---|---|
| 0 | 4 + 1 + 7 | 12 |
| 1 | 3 + 5 + 8 | 16 |
| 2 | 2 + 9 + 6 | 17 |

## B5. Cuadrado mágico

```
([ Inicio ])
      │
[ n = len(M) ]
[ objetivo = sum(M[0]) ]
      │
[ sumas = suma de cada fila ]            ← sum(fila) por cada fila
[ sumas += suma de cada columna ]        ← M[0][j]+M[1][j]+M[2][j]
[ sumas += diagonal principal ]          ← M[i][i]
[ sumas += diagonal secundaria ]         ← M[i][n-1-i]
      │
< ¿todas las sumas == objetivo? >
   │Sí                      │No
[/ "Es cuadrado magico" /]  [/ "No es cuadrado magico" /]
   └──────────┬─────────────┘
          ([ Fin ])
```

Traza con `M = [[2,7,6],[9,5,1],[4,3,8]]`:

```
    j=0 j=1 j=2
i=0  2   7   6   → 15
i=1  9   5   1   → 15
i=2  4   3   8   → 15
     ↓   ↓   ↓   ↘ diag ppal: 2+5+8 = 15
    15  15  15   ↙ diag sec.: 6+5+4 = 15
```

| Suma | Valor | ¿= 15? |
|---|---|---|
| fila 0, 1, 2 | 15, 15, 15 | Sí |
| col 0, 1, 2 | 15, 15, 15 | Sí |
| diagonal principal | 15 | Sí |
| diagonal secundaria | 15 | Sí |

Todas Sí → `Es cuadrado magico`

## B6. `transponer(M)`

```
([ Inicio transponer(M) ])
          │
      [ T = [] ]
          │
   ┌─►< ¿quedan columnas j de M? >──No──►[/ return T /]──►([ Fin ])
   │            │ Sí
   │      [ fila = [] ]
   │            │
   │   ┌─►< ¿quedan filas i de M? >──No──┐
   │   │         │ Sí                    │
   │   │  [ fila.append(M[i][j]) ]       │
   │   └─────────┘                       │
   │                          [ T.append(fila) ]
   └─────────────────────────────────────┘
```

Traza con `M = [[1,2,3],[4,5,6]]` (2×3 → 3×2):

| j | i=0 → M[0][j] | i=1 → M[1][j] | fila | T |
|---|---|---|---|---|
| 0 | 1 | 4 | [1,4] | [[1,4]] |
| 1 | 2 | 5 | [2,5] | [[1,4],[2,5]] |
| 2 | 3 | 6 | [3,6] | [[1,4],[2,5],[3,6]] |

---

# SEMANA 8 — RECURSIÓN, TUPLAS, DICCIONARIOS Y CONJUNTOS

## B1. `estadisticas(datos)`

```
([ Inicio estadisticas(datos) ])
              │
   [ minimo = datos[0] ]
   [ maximo = datos[0] ]
   [ total = 0 ]
              │
   ┌─►< ¿quedan x en datos? >──No──┐
   │          │ Sí                 │
   │   < ¿x < minimo? >──Sí──[ minimo = x ]
   │          │No                  │
   │   < ¿x > maximo? >──Sí──[ maximo = x ]
   │          │No                  │
   │   [ total = total + x ]       │
   └──────────┘                    │
                                   ▼
        [/ return minimo, maximo, total/len(datos) /]──►([ Fin ])
```

Traza con `[4, 7, 1, 9, 3]`:

| x | minimo | maximo | total |
|---|---|---|---|
| inicio | 4 | 4 | 0 |
| 4 | 4 | 4 | 4 |
| 7 | 4 | 7 | 11 |
| 1 | 1 | 7 | 12 |
| 9 | 1 | 9 | 21 |
| 3 | 1 | 9 | 24 |

Promedio = 24 / 5 = 4.8 → devuelve la tupla `(1, 9, 4.8)`.

## B2. `saludar(nombre, saludo="Hola")`

```
([ Inicio saludar(nombre, saludo) ])
              │
   < ¿el llamador pasó saludo? >
      │Sí                  │No
 [ usa su valor ]    [ saludo = "Hola" ]
      └────────┬───────────┘
   [/ return saludo + ", " + nombre /]
              │
          ([ Fin ])
```

- `saludar("Ana")` → no pasó saludo → `Hola, Ana`
- `saludar("Luis", "Buenos dias")` → pasó saludo → `Buenos dias, Luis`

## B3. `factorial(n)` recursivo

```
([ Inicio factorial(n) ])
          │
   < ¿n == 0? >
      │Sí            │No
 [/ return 1 /]   [ r = factorial(n-1) ]   ← se llama a sí misma
      │                    │
      │             [/ return n * r /]
      └────────┬───────────┘
          ([ Fin ])
```

Árbol de llamadas para `factorial(5)` (baja hasta el caso base y luego sube):

```
factorial(5)
 └─ 5 * factorial(4)
        └─ 4 * factorial(3)
               └─ 3 * factorial(2)
                      └─ 2 * factorial(1)
                             └─ 1 * factorial(0)
                                    └─ 1            ← caso base
```

Subida (cada nivel recibe el resultado del de abajo):

```
factorial(0) = 1
factorial(1) = 1 * 1   = 1
factorial(2) = 2 * 1   = 2
factorial(3) = 3 * 2   = 6
factorial(4) = 4 * 6   = 24
factorial(5) = 5 * 24  = 120
```

## B4. `suma_digitos(n)` recursivo

```
([ Inicio suma_digitos(n) ])
          │
   < ¿n < 10? >            (un solo dígito)
      │Sí                    │No
 [/ return n /]       [ ultimo = n % 10 ]
      │               [ resto  = n // 10 ]
      │               [ r = suma_digitos(resto) ]
      │               [/ return ultimo + r /]
      └──────────┬────────┘
            ([ Fin ])
```

Árbol de llamadas para `suma_digitos(347)`:

```
suma_digitos(347)       347 % 10 = 7,  347 // 10 = 34
 └─ 7 + suma_digitos(34)         34 % 10 = 4,  34 // 10 = 3
          └─ 4 + suma_digitos(3)         3 < 10 → caso base
                   └─ 3
```

Subida: `3` → `4 + 3 = 7` → `7 + 7 = 14`.

## B5. Frecuencia de palabras

```
([ Inicio ])
      │
[ frase = "el perro y el gato y el raton" ]
[ frecuencia = {} ]
[ palabras = frase.lower().split() ]
      │
┌─►< ¿quedan palabras? >──No──►[/ print frecuencia /]──►([ Fin ])
│          │ Sí
│   [ p = siguiente palabra ]
│   [ actual = frecuencia.get(p, 0) ]     ← 0 si p aún no existe
│   [ frecuencia[p] = actual + 1 ]
└──────────┘
```

Traza:

| p | get(p, 0) | frecuencia después |
|---|---|---|
| el | 0 | {el:1} |
| perro | 0 | {el:1, perro:1} |
| y | 0 | {el:1, perro:1, y:1} |
| el | 1 | {el:2, perro:1, y:1} |
| gato | 0 | {el:2, perro:1, y:1, gato:1} |
| y | 1 | {el:2, perro:1, y:2, gato:1} |
| el | 2 | {el:3, perro:1, y:2, gato:1} |
| raton | 0 | {el:3, perro:1, y:2, gato:1, raton:1} |

## B6. Operaciones de conjuntos

```
([ Inicio ])
      │
[ A = set(a) ]  → {Ana, Luis, Marta}
[ B = set(b) ]  → {Luis, Pedro, Ana}
      │
[/ A & B /]  intersección → en ambas
[/ A | B /]  unión        → todos sin repetir
[/ A - B /]  diferencia   → solo en A
      │
 ([ Fin ])
```

Diagrama de Venn:

```
   A solo        A ∩ B        B solo
  ┌───────┐   ┌─────────┐   ┌───────┐
  │ Marta │   │ Ana     │   │ Pedro │
  │       │   │ Luis    │   │       │
  └───────┘   └─────────┘   └───────┘
  A - B        A & B         B - A
  └───────────── A | B ───────────────┘
```
