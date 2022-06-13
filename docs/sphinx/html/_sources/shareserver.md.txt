The Seamless shareserver
========================

(This documentation is a stub)

The shareserver is to share Seamless cells via its REST API.
By default, the REST port is 5813
In addition, the shareserver sends notifications via Websocket connections, served at port 5138
The primary ways to interact with the share server are:

- The browser, for GET requests.
  http://localhost:5813/ctx/a will get the value of cell "a", if it has been shared

- The seamless-http-put command, for PUT requests.

- The seamless client (seamless-client.js)
