seamless_read_cells = {
  "text": [],
  "json": [
    "a",
    "b",
    "c"
  ]
}
seamless_write_cells = {
  "text": [],
  "json": [
    "a",
    "b"
  ]
}

ctx = connect_seamless()
ctx.self.onsharelist = function(sharelist) {
    sharelist.forEach(element => {
        if (seamless_read_cells["json"].indexOf(element) >= 0) {
            ctx[element].onchange = function() {
                const v = JSON.parse(this.value)
                vm[element] = v
            }
        }
        else if (seamless_read_cells["text"].indexOf(element) >= 0) {
            ctx[element].onchange = function() {
                vm[element] = this.value
            }
        }
    })
}

function seamless_update(cell, value, encoding) {
  if (!ctx) return
  if (!ctx.self.sharelist) return
  if (ctx.self.sharelist.indexOf(cell) < 0) return
  if (encoding == "json") {
    ctx[cell].set(JSON.stringify(value))
  }
  else if (encoding == "text") {
    ctx[cell].set(value)
  }
}

const app = new Vue({
  data() {
    return {
      "a": 0,
      "b": 0,
      "c": 0
    }
  },
  watch: {
    a: function (value) {
        seamless_update("a", value, "json")
        },
    b: function (value) {
        seamless_update("b", value, "json")
        },
    
  }
})

vm = app.$mount('#app')
