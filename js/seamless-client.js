//https://raw.githack.com/sjdv1982/seamless/master/seamless-client.js



function connect_seamless(websocketserver, restserver, namespace="ctx"){  
  var ctx = {
    self: {
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
  let handshake = null
  let sharelist = null    
  
  function get_value(key) {
    var rq = restserver + "/" + namespace + "/" + key + "?mode=all"
    //$("#request").text("GET:" + rq)
    fetch(rq)
    .then(function(response) {
      return response.json()  
    })
    .then(function(result) {
      //$("#message").text(JSON.stringify(result))
      if (result["marker"] <= ctx[key]._marker) return
      ctx[key].value = result["buffer"]
      ctx[key]._marker = result["marker"]
      ctx[key].checksum = result["checksum"]
      ctx[key].oninput()
      ctx[key].onchange()
      ctx.self.oninput()
      ctx.self.onchange()
    })
    .catch(function(err) {
      console.log('Seamless client, GET Error:', key, err)
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
    var rq = restserver + "/" + namespace + "/" + key
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
      console.log('Seamless client PUT Error:', namespace, key, err)
    })
  }
  
  function onmessage(event) {
    var message = JSON.parse(event.data);
    if (handshake == null) {
      handshake = message
      //$("#message").text(JSON.stringify(handshake))
    }    
    else if (message[0] == "sharelist") {
      sharelist = message[1];
      //$("#message").text(JSON.stringify(sharelist))
      function curry_set_value(bound_key) {
        return function(value) {
          return set_value(bound_key, value)
        }
      }
      for (const key of sharelist) {        
        if (key == "self") continue
        ctx[key] = {
          value: null,
          _marker: null,
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
      //$("#message").text(JSON.stringify(message))
      if (ctx[key]._marker == null || ctx[key]._marker < marker) {
        get_value(key)
      }
    }
    else {
      console.log('Seamless client websocket Error: unknown message format:', message)
      //$("#message").text(message) 
    }
  }
  var ws_url = websocketserver + "/" + namespace
  var ws = new WebSocket(ws_url)
  ws.onmessage = onmessage;  
  
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

ctx = connect_seamless("ws://localhost:5138", "http://localhost:5813" );
ctx.self.onsharelist = function(sharelist) {
  ctx.cell1.onchange = function() {
    data = ctx.cell1.value
    $("#model").text(data)
  }
}
*/