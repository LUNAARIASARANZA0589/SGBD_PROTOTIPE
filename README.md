## Creación del Prototipo
**Librerías utilizadas para la manipulación de los archivos:** 
Pymongo: Utilizado para la conectividad entre la interfaz y el servidor que almacena todos los datos, en este caso, MongoDB atlas, mediante el cual fabricamos un cluster(un mini servidor) al cual nos conectamos por medio de una URL y una contraseña. 
Pandas: Nos permite leer archivos .xlxs (formato de las hojas de cálculo de Excel y Google Sheets), permitiéndonos manipularlas para transformarlas en tablas y posteriormente en archivos JSON para que sean debidamente procesados por MongoDB. 
Openpyxl: Es una ramita de Pandas, nos permite dar formato a las hojas de cálculo y manipularlas, para adaptar los archivos que se importen a la página y encajen con los criterios que pedimos para la base de datos.
Json: La utiizamos para convertir cadenas Python a cadenas JSON, y así poder manipular nuestros documentos en MongoDB de una manera más sencilla. 
Bson: Nos permite interactuar más allá con MongoDB, nos permite interactuar con sus identificadores internos y así podemos buscar documentos específicos por su ID. 

**Librerías utilizadas para la interfaz:**
Flask: Es el framework que levanta toda la página, con ella renderizamos los templates(los HTML que muestran en el navegador el inicio y el login) y hacemos todas las peticiones HTTP como GET, POST y maneja las rutas de navegación. 
Warkzeug: Nos permite elaborar hash de contraseñas (cifrarlas), así podemos guadar contraseñas sin tener que manipular información sensible. Las contraseñas se guardan como una bolita de plastilina revuelta que tiene ciertos colores específicos. 

**Generación de reportes:**
reportlab: Es la librería que se encarga de hacer los PDFs que pueden descargasrse en la página, puede definirse una estructura completa dentro de un template con reportlab y así importarse como un PDF. 
