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
        vm[cell].value = v
        vm[cell].checksum = this.checksum
      }
    }
    else if (seamless_read_cells["json"].indexOf(cell) >= 0) {
      ctx[cell].onchange = function () {
        try {
          const v = JSON.parse(this.value)
          vm[cell].value = v
          vm[cell].checksum = this.checksum
        }
        catch (error) {
          console.log(`Cannot parse server value of cell '${cell}' as JSON`)
        }
      }
    }
    else if (seamless_read_cells["text"].indexOf(cell) >= 0) {
      ctx[cell].onchange = function () {
        vm[cell].value = this.value
        vm[cell].checksum = this.checksum
      }
    }

    if (seamless_auto_read_cells.indexOf(cell) >= 0) {
      ctx[cell].auto_read = true
    }
  })
}
webctx = connect_seamless(null, null, share_namespace="status")
webctx.self.onsharelist = function (sharelist) {
  vis_status = webctx["vis_status"]
  if (!(vis_status === undefined)) {
    vis_status.onchange = function() {      
      let jstatus = JSON.parse(vis_status.value)
      cells = {}
      transformers = {}
      jstatus.nodes.forEach(node => {
        if (node.type == "cell") {
          cells[node.name] = node
        }
        else if (node.type == "transformer") {
          transformers[node.name] = node
        }
      })
      jstatus.cells = cells
      jstatus.transformers = transformers
      vm["STATUS"].value = jstatus
      vm["STATUS"].checksum = vis_status.checksum
    }
  }
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
    return {
      ...{{ VUE_DATA }}, 
      ...{
        "STATUS": {
          "checksum": null,
          "value": {}
        }
      }
    }
  },
  methods: {
    METHOD_get_app_globals() {
      return app_globals
    },
    METHOD_file_upload(cellname, file) { 
      if (file === undefined) return
      that = this
      file.arrayBuffer().then(function(buf){
        that[cellname].value = new Blob([new Uint8Array(buf)], {type: file.type })
      })  
    }
    
  },
  watch: {
    {{WATCHERS}}
  },
})

vm = app.$mount('#app')
