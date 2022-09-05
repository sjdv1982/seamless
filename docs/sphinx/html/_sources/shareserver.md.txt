# The Seamless shareserver

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

**Relevant examples:**

- [basic example](https://github.com/sjdv1982/seamless/tree/stable/examples)

- [webserver demo](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-demo)

- [webserver example](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-example)

- [datatables](https://github.com/sjdv1982/seamless/tree/stable/examples/datatables-example)

- [grid editor](https://github.com/sjdv1982/seamless/tree/stable/examples/grid-editor-example)

The shareserver is to share Seamless cells via its REST API.
By default, the REST port is 5813
In addition, the shareserver sends notifications via Websocket connections, served at port 5138
The primary ways to interact with the share server are:

- The browser, for GET requests.
  http://localhost:5813/ctx/a will get the value of cell "a", if it has been shared

- The seamless-http-put command, for PUT requests.

- The seamless client (seamless-client.js)

## HTTP sharing

Intro:

- share
- cell.mimetype
- REST
- Your own web page, Seamless as file server (link to beginner gotchas)
