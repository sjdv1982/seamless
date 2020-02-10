function connect_seamless(update_server=null, rest_server=null, share_namespace="ctx"){    
  var ctx = {
    self: {
      parse_ports: function(update_server, rest_server) {
        http_port = window.location.port
        if (update_server == null) {
          if (http_port == 80 || http_port == 8080 || http_port == 3124 || http_port == "") {
            // assume that we are behind a reverse proxy, or Cloudless (3124)
            // that redirects both http(s):// and ws(s)://
            update_server = http_port
          }
          else {
            update_server = 5138
          }
        }
        http_protocol = window.location.protocol
        if (http_protocol == "https:") {
          ws_protocol = "wss:"
        }
        else {
          ws_protocol = "ws:"
        }        
        var Uhost = window.location.hostname
        var pathArray = window.location.pathname.split('/')
        var Upath = ""
        for (i = 0; i < pathArray.length - 2; i++) {
          if (pathArray[i] == "") continue;
          Upath += "/";
          Upath += pathArray[i];
        }
        if (Upath == "") Upath = "/"
        if (update_server == "") {
          update_server = ws_protocol + "//" +  Uhost + Upath
        }
        else {
          update_port = parseInt(update_server)
          if (typeof(update_port) == "number") {
            update_server = ws_protocol + "//" +  Uhost + ":" + update_port + Upath          
          }
        }
        if (rest_server == null) {
          rest_server = http_port
        }
        if (rest_server == "") {
          rest_server = http_protocol + "//" +  Uhost + Upath
        }
        else {
          rest_port = parseInt(rest_server)
          if (typeof(rest_port) == "number") {
            rest_server = http_protocol + "//" +  Uhost + ":" + rest_port + Upath
          }
        }
        update_server = update_server.replace(/\/$/, "")
        rest_server =  rest_server.replace(/\/$/, "")
        this.update_server = update_server
        this.rest_server = rest_server
      },
      share_namespace: share_namespace,
      oninput: function(value) {},
      onchange: function(value) {},
      onsharelist: function(value) {},
      get_value: function(){
        let result = {}
        for (const key of sharelist) {
          result[key] = ctx[key].value
        }
        return result
      }
    }
  }
  ctx.self.parse_ports(update_server, rest_server)
  
  let handshake = null
  let sharelist = null    
  
  function get_value(key) {
    var rq = ctx.self.rest_server + "/" + ctx.self.share_namespace + "/" + key + "?mode=marker"
    //$("#request").text("GET:" + rq)
    //$("#error_message").text("GET:" + rq)
    fetch(rq)
    .then(function(response) {
      return response.json()  
    })
    .then(function(result) {
      if (result["marker"] <= ctx[key]._marker) return
      ctx[key]._marker = result["marker"]
      ctx[key].checksum = result["checksum"]  
      return result    
    })
    .then(async function(result){
      if (ctx[key].auto_read) {
        var rq2 = ctx.self.rest_server + "/" + ctx.self.share_namespace + "/" + key + "?mode=buffer"
        //$("#error_message").text("GET:" + rq2)
        //$("#error_message").text(result)
        const response = await fetch(rq2)
        r = await response.text()
        //$("#error_message").text("RESP:" + r)
        ctx[key].value = r                
      }
    })
    .catch(function(err) {
      console.log('Seamless client, GET Error:', key, err)
    })
    .finally(function(arg){
      ctx[key].oninput()
      ctx[key].onchange()
      ctx.self.oninput()
      ctx.self.onchange()
    })
  }
  function set_value(key, value) {
    console.log(key)
    ctx[key].value = value;
    ctx[key].oninput()
    ctx.self.oninput()
    put_value(key, value)
  }
  function put_value(key, value) { 
    var rq = ctx.self.rest_server + "/" + ctx.self.share_namespace + "/" + key
    if (ctx[key]._marker == null) ctx[key]._marker = 0
    oldmarker = ctx[key]._marker 
    newmarker = oldmarker + 1
    const payload = JSON.stringify({
      "buffer":value,
      "marker":newmarker
    })
    //$("#request").text(JSON.stringify({"rq": "PUT:" + rq, "buffer": value}))
    let options = {
      method: "PUT", 
      body: payload,    
      headers: {
        "Content-Type": "application/json; charset=utf-8",
      }
    }
    fetch(rq, options)
    .then(function(response) {
      return response.text()
    })
    .then(function(result) {
      if (parseInt(result)) {
        if (ctx[key]._marker == oldmarker) {
          ctx[key]._marker = newmarker
        }
      }
    })
    .catch(function(err) {
      console.log('Seamless client PUT Error:', ctx.self.share_namespace, key, err)
    })
  }
  
  function onmessage(event) {
    var message = JSON.parse(event.data);
    if (handshake == null) {
      handshake = message
      //$("#error_message").text(JSON.stringify(handshake))
    }    
    else if (message[0] == "sharelist") {
      sharelist = message[1];
      //$("#error_message").text(JSON.stringify(sharelist))
      function curry_set_value(bound_key) {
        return function(value) {
          return set_value(bound_key, value)
        }
      }
      for (const key of sharelist) {        
        if (key == "self") continue
        auto_read = (key.indexOf('.') == -1)
        ctx[key] = {
          value: null,
          _marker: null,
          initial: true,
          auto_read: auto_read,
          set: curry_set_value(key),
          oninput: function(value) {},
          onchange: function(value) {},
        }
        get_value(key)
      }
      ctx.self.onsharelist(sharelist)
    }
    else if (message[0] == "update") {
      let key = message[1][0]
      let marker = message[1][2]
      //$("#error_message").text(JSON.stringify(message))
      if (ctx[key]._marker == null || ctx[key]._marker < marker) {
        get_value(key)
        ctx[key].initial = false
      }
    }
    else {
      console.log('Seamless client websocket Error: unknown message format:', message)
      //$("#error_message").text(message) 
    }
  }
  ctx.self.connect = function() {
    var ws_url = ctx.self.update_server + "/" + ctx.self.share_namespace
    ctx.self.ws = new WebSocket(ws_url)
    ctx.self.ws.onmessage = onmessage;  
  }
  ctx.self.connect()
  return ctx
}


if (typeof define !== 'undefined') { //require.js
  define({
    connect_seamless: connect_seamless,
  });
}
if (typeof module !== 'undefined') {  
  module.exports = {
    connect_seamless: connect_seamless,
  };
}

/*
// Example:

ctx = connect_seamless(5138, 5813);
ctx.self.onsharelist = function(sharelist) {
  ctx.cell1.onchange = function() {
    data = ctx.cell1.value
    $("#model").text(data)
  }
}
*/
