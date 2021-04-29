app_globals = {}

{{ COMPONENT_JS }}

seamless_read_cells = {{ SEAMLESS_READ_CELLS }}
seamless_write_cells = {{ SEAMLESS_WRITE_CELLS }}
seamless_auto_read_cells = {{ SEAMLESS_AUTO_READ_CELLS }}

ctx = connect_seamless()
ctx.self.onsharelist = function (sharelist) {
  sharelist.forEach(cell => {
    if (ctx[cell].binary) {
      ctx[cell].onchange = function () {
        content_type = ctx[cell].content_type
        if (content_type === null) content_type = ""
        const v = new Blob([this.value], {type: content_type})
        vm[cell] = v
      }
    }
    else if (seamless_read_cells["json"].indexOf(cell) >= 0) {
      ctx[cell].onchange = function () {
        try {
          const v = JSON.parse(this.value)
          vm[cell] = v
        }
        catch (error) {
          console.log(`Cannot parse server value of cell '${cell}' as JSON`)
        }
      }
    }
    else if (seamless_read_cells["text"].indexOf(cell) >= 0) {
      ctx[cell].onchange = function () {
        vm[cell] = this.value
      }
    }

    if (seamless_auto_read_cells.indexOf(cell) >= 0) {
      ctx[cell].auto_read = true
    }
  })
}

function seamless_update(cell, value, encoding) {
  if (!ctx) return
  if (!ctx.self.sharelist) return
  if (ctx.self.sharelist.indexOf(cell) < 0) return
  if (ctx[cell].binary) {
    ctx[cell].set(value)
  }
  else if (encoding == "json") {
    ctx[cell].set(JSON.stringify(value))
  }
  else if (encoding == "text") {
    ctx[cell].set(value)
  }
}

const app = new Vue({
  vuetify: new Vuetify(),
  data() {
    return {{ VUE_DATA }}
  },
  methods: {
    get_app_globals() {
      return app_globals
    },
    METHOD_file_upload(cellname, file) {  // use METHOD_ to minimize the risk of name clashes with cell names
      if (file === undefined) return
      that = this
      file.arrayBuffer().then(function(buf){
        that[cellname] = new Blob([new Uint8Array(buf)], {type: file.type })
      })  
    }
  },
  watch: {
    {{WATCHERS}}
  }
})

vm = app.$mount('#app')
