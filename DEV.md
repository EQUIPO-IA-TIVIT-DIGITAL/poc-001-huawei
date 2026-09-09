# DEV.md — Estándares de Desarrollo y Despliegue

Documento de requisitos que todo proyecto debe cumplir antes de ser considerado apto para despliegue. Esta guía garantiza reproducibilidad, seguridad, contenerización, documentación y trazabilidad del código.

> **Nota:** cada sección define criterios obligatorios. El incumplimiento de cualquier criterio debe justificarse explícitamente antes de solicitar el despliegue.

---

## 1. Estructura y Organización

- [ ] Diferenciar claramente: código fuente, pruebas automatizadas, documentación, configuración, dependencias, archivos de build/ejecución y archivos de contenedores.
- [ ] Excluir del repositorio archivos temporales, binarios generados, dependencias descargadas, configuraciones locales de IDE y cachés.
- [ ] Incluir obligatoriamente un archivo `.gitignore` configurado.
- [ ] Incluir un archivo `.dockerignore` si el proyecto utiliza Docker.

---

## 2. Documentación (README.md Obligatorio)

El `README.md` debe incluir:

- [ ] Nombre, descripción y objetivo del proyecto.
- [ ] Arquitectura o componentes principales (si aplica).
- [ ] Tecnologías y versión requerida del lenguaje/runtime.
- [ ] Dependencias principales y requisitos previos.
- [ ] Pasos para instalación, ejecución local y ejecución de pruebas.
- [ ] Variables de entorno requeridas y puertos utilizados.
- [ ] Servicios externos y bases de datos requeridas.
- [ ] Procedimiento de construcción (build).
- [ ] Consideraciones relevantes para el despliegue.
- [ ] Debe ser comprensible para terceros sin depender del conocimiento del desarrollador.

---

## 3. Dependencias y Reproducibilidad

- [ ] Declarar explícitamente todas las dependencias mediante manifiestos estándar (`package.json`, `requirements.txt`, `go.mod`, etc.).
- [ ] Mantener archivos de bloqueo (lock files) para garantizar builds reproducibles.
- [ ] Controlar versiones para evitar quiebres por incompatibilidad futura.
- [ ] No depender de paquetes instalados manualmente a nivel local.
- [ ] El proyecto debe poder compilarse/construirse desde cero utilizando únicamente lo versionado, las dependencias declaradas y la configuración externa.

---

## 4. Contenerización (Dockerfile y .dockerignore)

- [ ] Contar con un `Dockerfile` funcional que construya desde cero con `docker build` y arranque sin ajustes manuales.
- [ ] Usar imágenes base oficiales o aprobadas, con versiones fijas (evitar tag `latest`).
- [ ] Instalar solo dependencias requeridas y no incluir archivos innecesarios.
- [ ] Prohibido incluir secretos, contraseñas o tokens en la imagen.
- [ ] Exponer únicamente los puertos necesarios.
- [ ] Usar multi-stage builds cuando convenga y ejecutar con usuario no-root siempre que sea posible.
- [ ] Mantener la imagen lo más ligera y segura posible.
- [ ] Excluir del contexto vía `.dockerignore`: `.git`, `.env`, cachés, dependencias locales, logs, temporales, etc.

---

## 5. Configuración y Variables de Entorno

- [ ] No quemar (hardcodear) configuraciones variables entre ambientes (URLs, hosts, puertos, DBs, flags).
- [ ] Proveer un archivo `.env.example` con las variables requeridas (solo como plantilla de referencia).
- [ ] Prohibir secretos o valores reales dentro de `.env.example`.
- [ ] Mantener el archivo `.env` real listado en el `.gitignore`.

---

## 6. Gestión de Secretos y Seguridad

- [ ] Prohibición absoluta de almacenar contraseñas, tokens, API keys, certificados o credenciales en el código o en el historial de Git.
- [ ] Inyectar secretos exclusivamente vía gestores de secretos o variables protegidas del pipeline.
- [ ] Notificar de inmediato y rotar cualquier credencial expuesta accidentalmente en el historial.
- [ ] Mantener dependencias actualizadas y soportar escaneos automáticos (SCA, SAST, secret scanning, container scanning).
- [ ] Resolver vulnerabilidades críticas o de severidad alta antes de pasar a producción.

---

## 7. Operabilidad y Diagnóstico

- [ ] Endpoint de monitoreo implementado (estándar: `GET /health`), con endpoints adicionales (liveness, readiness, startup) si aplica.
- [ ] Logs emitidos preferentemente hacia `stdout` y `stderr` (no depender de archivos internos del contenedor).
- [ ] Prohibido escribir datos sensibles o credenciales en los logs.
- [ ] Manejo adecuado de inicio y salida con códigos de término apropiados; soportar *graceful shutdown*.
- [ ] No asumir persistencia en el filesystem del contenedor; usar volúmenes, object storage o bases de datos y documentarlo.

---

## 8. Pruebas y Calidad de Código

- [ ] Incluir pruebas automatizadas con el comando de ejecución claramente definido (`npm test`, `pytest`, etc.).
- [ ] Las pruebas deben pasar exitosamente de forma desatendida; no se despliega con pruebas fallidas sin excepción aprobada.
- [ ] Definir y soportar herramientas de calidad en CI (linters, formatters, type checking, análisis estático).

---

## 9. Base de Datos y Migraciones

- [ ] Gestionar cambios de esquema mediante herramientas de migración reproducibles y versionadas en el repo (Alembic, Prisma, Flyway, etc.).
- [ ] No depender de alteraciones manuales directas sin trazabilidad.
- [ ] Documentar cómo y en qué fase ejecutarlas (antes, durante o después del despliegue).

---

## 10. Control de Versiones y Flujo de Trabajo

- [ ] Todo despliegue debe asociarse a un repositorio, branch, commit y tag/versión específica (preferencia por versionado semántico: `vX.Y.Z`).
- [ ] Prohibido solicitar despliegues basados en términos ambiguos ("la última versión").
- [ ] Proteger ramas principales y trabajar mediante PR/MR con revisión obligatoria (code review).

---

## 11. Integración CI/CD y Recursos

- [ ] El repositorio debe estar listo para integrarse a pipelines automatizados (dependencias → lint → test → seguridad → build → empaquetado → despliegue).
- [ ] Documentar requisitos de infraestructura: puertos, protocolos, dependencias de red, CPU/RAM, y requerimientos especiales como GPU, VRAM o modelos para proyectos de IA.
- [ ] Documentar todas las dependencias y servicios externos (Postgres, Redis, Kafka, APIs, storage, etc.) y las variables que controlan su conexión.

---

## 12. Independencia del Entorno Local

- [ ] La aplicación no debe depender de "funcionar en la máquina del desarrollador".
- [ ] Cero dependencias implícitas: sin rutas absolutas locales, archivos locales no versionados, ni bases de datos no declaradas.
- [ ] Cualquier excepción por limitaciones técnicas o legadas debe documentarse explícitamente antes de solicitar el despliegue.
