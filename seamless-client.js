function connect_seamless(websocketserver, restserver, namespace="ctx"){  
  var ctx = {
    self: {
      oninput: function(value) {},
      onchange: function(value) {},
      onvarlist: function(value) {},
      get_value: function(){
        let result = {}
        for (const key of varlist) {
          result[key] = ctx[key].value
        }
        return result
      }
    }
  }
  let handshake = null
  let varlist = null    
  
  function get_value(key) {
    var rq = "http://" + restserver + "/" + namespace + "/" + key
    //$("#request").text("GET:" + rq)
    fetch(rq)
    .then(function(response) {
      if (response.headers.get("Content-Type") == "application/json"){
        return response.json()  
      }
      else {
        return response.text()
      }
    })
    .then(function(result) {
      ctx[key].value = result
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
    var rq = "http://" + restserver + "/" + namespace + "/" + key
    const payload = JSON.stringify({"value":value})
    //$("#request").text(JSON.stringify({"rq": "PUT:" + rq, "value": value}))
    let options = {
      method: "PUT", 
      body: payload,    
      headers: {
        "Content-Type": "application/json; charset=utf-8",
      }
    }
    if (ctx[key]._marker == null) ctx[key]._marker = 0
    ctx[key]._marker++;
    fetch(rq, options)
    .then(function(response) {
      return response.text()
    })
    .then(function(result) {
      ctx[key]._marker = parseInt(result);
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
    else if (message[0] == "varlist") {
      varlist = message[1];
      //$("#message").text(JSON.stringify(varlist))
      function curry_set_value(bound_key) {
        return function(value) {
          return set_value(bound_key, value)
        }
      }
      for (const key of varlist) {
        ctx[key] = {
          value: null,
          _marker: null,
          set: curry_set_value(key),
          oninput: function(value) {},
          onchange: function(value) {},
        }
        get_value(key)
      }
      ctx.onvarlist(varlist)
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
  var ws_url = "ws://" + websocketserver + "/" + namespace
  var ws = new WebSocket(ws_url)
  ws.onmessage = onmessage;  
  
  return ctx
}


//export default connect_seamless
define({
  connect_seamless: connect_seamless,
});
/*
module.exports = {
  connect_seamless: connect_seamless,
};
*/
