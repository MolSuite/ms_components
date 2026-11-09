# Temas Spectrum y contraste teal frente a `catppuccin_mocha`

Paleta oscura `spectrum_dark_teal` añadida a `src/ms_components/palettes.py`, con los mismos
29 keywords que `catppuccin_mocha`. No faltaba ningún rol.

La familia ahora ofrece 21 colores primarios en dos modos, con el menú
`Spectrum themes → Light / Dark → Color`, tanto en el botón de tema de AMDockVS
como en Ajustes. `build_theme_menu` y `ThemeComboBox` viven en `ms_components.theme`;
ambos selectores comparten la misma jerarquía y mantienen una única selección.
Las 42 variantes conservan las mismas claves y cumplen los mínimos de contraste
exigidos por las pruebas de paletas. Solo cambian `highlight`, `accent`, `link` y
`link_visited` al elegir otro color dentro del mismo modo.

Los ids guardados son `spectrum_light_<color>` y `spectrum_dark_<color>`.
Los nombres anteriores `zensical_light_<color>`, `zensical_dark_<color>` y
`zensical_teal` se resuelven a sus equivalentes Spectrum, sin duplicarse en el menú.
La selección global `Auto` conserva su comportamiento previo.

Spectrum es una adaptación independiente para MolSuite. Agradecemos a los
colaboradores de Zensical el diseño de las paletas originales que la inspiraron;
no son temas oficiales de Zensical. El menú también muestra este reconocimiento
en su tooltip.

Referencia: [colores de Zensical](https://zensical.org/docs/setup/colors/) y su
[CSS modern](https://zensical.org/docs/assets/stylesheets/modern/palette.b60ce83d.min.css),
consultados el 2026-11-08. Se conservan el enlace teal oscuro `#00ccb8` y el acento
`#00bda4`; las superficies se inspiran en slate (`#0b0c0f`, `#16171a`, `#212226`).
Los demás colores se adaptan a los roles de Qt y sus requisitos de contraste.
En especial, los primarios claros (amarillo, lima, blanco, etc.) se oscurecen en
modo Light para que funcionen como texto y foco sobre fondos claros. Se ofrece
un color principal por variante, con su acento coordinado; no hay un selector
independiente para combinar cualquier primario con cualquier acento.

Los ratios se calcularon con `ms_components.theme.contrast_ratio` (luminancia relativa
sRGB, WCAG), sin redondear antes de comprobar los límites. Los números de las tablas
son ratios «n:1», redondeados a dos decimales. Se revisaron `theme.py`, `base.qss`,
`ms_stepper.py`, la barra de herramientas de tablas y sus celdas de progreso.

## Texto y selección

Umbral de referencia: 4.5:1 para texto normal. Todas estas combinaciones del nuevo
tema lo alcanzan, incluida la metadata de la barra de tablas sobre `dark`.

| Texto / fondo | Mocha | Teal |
| --- | ---: | ---: |
| `window_text` / `window` | 11.34 | 10.60 |
| `text` / `window` | 11.34 | 10.60 |
| `text` / `base` | 12.14 | 11.57 |
| `text` / `alternate_base` | 11.34 | 9.40 |
| `button_text` / `button` | 11.34 | 10.60 |
| `tooltip_text` / `tooltip_base` | 6.22 | 6.68 |
| `text` / `dark` | 6.31 | 6.53 |
| `placeholder_text` / `window` | 4.62 | 7.53 |
| `placeholder_text` / `base` | 4.95 | 8.22 |
| `placeholder_text` / `alternate_base` | 4.62 | 6.68 |
| `placeholder_text` / `dark` | 2.57 | 4.64 |
| `highlighted_text` / `highlight` | 9.23 | 8.21 |

El QSS de tooltips usa `text` / `window`, además de los roles de tooltip nativos.
`window_text` y `button_text` tienen el mismo valor que `text` en ambas paletas;
sus combinaciones equivalentes tienen los mismos ratios.

## Enlaces y colores semánticos

Cada celda muestra los ratios sobre `window` / `base` / `alternate_base`, en ese
orden. Todos superan 4.5:1; el mínimo del tema teal en este grupo es 6.25:1.

| Keyword | Mocha | Teal |
| --- | ---: | ---: |
| `link` | 7.79 / 8.34 / 7.79 | 8.82 / 9.62 / 7.82 |
| `link_visited` | 7.79 / 8.34 / 7.79 | 8.82 / 9.62 / 7.82 |
| `accent` | 7.79 / 8.34 / 7.79 | 7.52 / 8.21 / 6.67 |
| `red` | 7.08 / 7.58 / 7.08 | 7.11 / 7.76 / 6.30 |
| `orange` | 9.27 / 9.92 / 9.27 | 9.26 / 10.10 / 8.21 |
| `yellow` | 12.91 / 13.81 / 12.91 | 9.21 / 10.05 / 8.17 |
| `green` | 11.03 / 11.81 / 11.03 | 8.18 / 8.92 / 7.25 |
| `cyan` | 10.54 / 11.29 / 10.54 | 9.09 / 9.92 / 8.06 |
| `blue` | 7.79 / 8.34 / 7.79 | 7.52 / 8.20 / 6.66 |
| `magenta` | 8.07 / 8.64 / 8.07 | 7.05 / 7.69 / 6.25 |

## Bordes, foco y superficies

Para bordes de controles y foco se usa 3:1. El mínimo de `shadow` sobre las tres
superficies principales sube de 3.36 a 4.78; también alcanza 3:1 sobre `dark`.

| Elemento / superficie | Mocha | Teal |
| --- | ---: | ---: |
| `highlight` / `window` | 8.07 | 7.52 |
| `highlight` / `base` | 8.64 | 8.21 |
| `highlight` / `alternate_base` | 8.07 | 6.67 |
| `highlight` / `dark` | 4.49 | 4.63 |
| `shadow` / `window` | 3.36 | 5.39 |
| `shadow` / `base` | 3.59 | 5.88 |
| `shadow` / `alternate_base` | 3.36 | 4.78 |
| `shadow` / `dark` | 1.87 | 3.31 |
| `dark` / `base` | 1.92 | 1.77 |
| `dark` / `alternate_base` | 1.80 | 1.44 |
| `mid` / `window` | 2.46 | 2.29 |
| `highlight` / `midlight` | 8.64 | 6.67 |
| `light` / `window` | 1.14 | 1.09 |

`dark` es la banda de cabecera: ambas paletas cumplen el mínimo decorativo de 1.4
que exige el proyecto. `mid` son separadores decorativos y `light` es un rol de
relieve nativo; no se interpretan aquí como texto ni como bordes de controles.
`bright_text` conserva el rol nativo de Qt, sin pareja explícita en el QSS revisado;
en teal coincide con `highlighted_text`.

## Otros estados y límites encontrados

| Texto / fondo | Mocha | Teal | Uso |
| --- | ---: | ---: | --- |
| `highlighted_text` / `highlight` oscurecido con `darker(112)` | 7.38 | 6.59 | Hover de «siguiente» del stepper |
| `highlighted_text` / `red` | 8.10 | 7.76 | Indicador de error del stepper |
| `highlighted_text` / `orange` | 10.59 | 10.10 | Indicador de aviso del stepper |
| `highlighted_text` / `mid` | 2.81 | 2.50 | Toolbuttons pulsados/seleccionados con fondo `mid` |
| `placeholder_text` / `mid` | 1.88 | 3.29 | «Siguiente» deshabilitado |
| `disabled_text` / `window` | 2.65 | 2.94 | Controles deshabilitados |
| `disabled_text` / `mid` | 1.08 | 1.28 | Selección deshabilitada de QPalette |

Los toolbuttons con texto `highlighted_text` y fondo `mid` quedan por debajo de
4.5:1 en ambos temas: el QSS específico cambia el fondo, pero hereda el color del
estado general. Los controles deshabilitados están exentos del umbral de texto
activo; se mantiene la jerarquía `disabled_text` < `placeholder_text` < `text`.

Las celdas de progreso mezclan `red` o `green` con `dark` usando alfa 150/255.
Se comprobó con `QProgressBar.grab()` en Qt offscreen que el texto del estilo
actual se aproxima a `text`, no a `highlighted_text`. El contraste calculado entre
ese texto y el relleno compuesto es:

| Texto / relleno compuesto | Mocha | Teal |
| --- | ---: | ---: |
| `text` / `red` alfa 150 sobre `dark` | 2.71 | 2.67 |
| `text` / `green` alfa 150 sobre `dark` | 1.95 | 2.37 |

Estas barras tampoco alcanzan 4.5:1 en ninguno de los temas. Alcanzar los mínimos
de la paleta no garantiza el contraste de los colores mezclados por un widget.
No se cambia el QSS compartido ni el renderizado de barras en este cambio de tema.

## Validación

Pruebas ejecutadas con el Python de conda `MSDD_312`, `PYTHONPATH=src` y
`QT_QPA_PLATFORM=offscreen`: contraste de todas las paletas, igualdad de keywords,
resolución del nombre nuevo, bordes renderizados de checkbox/radio en ambos temas,
y compatibilidad de importación de paletas sin Qt. La ampliación añade pruebas de
los 42 temas, la jerarquía del menú, exclusividad entre submenús, selección real en
el popup de Ajustes, compatibilidad del editor genérico de configuración y
persistencia de nombres nuevos/antiguos. También se verifica que seleccionar
`Spectrum themes → Dark → Teal` en la ventana de AMDockVS aplica y guarda el tema.

**29 pruebas pasaron**: 20 de componentes y 9 de integración/persistencia en AMDockVS.
`git diff --check` pasó en ambos repositorios. No se hizo revisión visual en pantalla;
las comprobaciones de widgets se ejecutaron con Qt offscreen.
