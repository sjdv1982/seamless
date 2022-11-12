app_globals = {}

function load_ngl(stage, pdbs, representations){
    stage.removeAllComponents()
    Object.keys(pdbs).forEach(function(item){
        let pdb = new Blob([pdbs[item]], {type : 'text/plain'})
        stage.loadFile(pdb, { ext: "pdb" } ).then(function (o) {            
            let curr_representations = representations[item]
            if (curr_representations === null || curr_representations === undefined) curr_representations = representations["DEFAULT"]
            if (curr_representations === null || curr_representations === undefined) return
            if (!Array.isArray(curr_representations)) curr_representations = [curr_representations]
            Object.keys(curr_representations).forEach(function(repnr){
                let rep = curr_representations[repnr]
                o.addRepresentation(rep["type"], {...rep["params"]})
            })
            o.autoView();
        })        
    })
}



seamless_read_paths = {
  "text": [],
  "json": [
    "sub__mycell",
    "struc",
    "nglviewer_1__representation.json"
  ]
}
seamless_write_paths = {
  "text": [],
  "json": []
}
seamless_auto_read_paths = [
  "sub__mycell",
  "struc",
  "nglviewer_1__representation.json"
]
seamless_path_to_cell = {
  "struc": "structures",
  "nglviewer_1__representation.json": "representation"
}

ctx = connect_seamless()
ctx.self.onsharelist = function (sharelist) {
  sharelist.forEach(path0 => {
    let path = path0.replaceAll("/", "__")
    cell0 = seamless_path_to_cell[path]
    if (cell0 === undefined) cell0 = path0
    let cell = cell0.replaceAll("/", "__")
    if (ctx[path].binary) {
      ctx[path].onchange = function () {
        content_type = ctx[path].content_type
        if (content_type === null) content_type = ""
        const v = new Blob([this.value], {type: content_type})
        vm[cell].value = v
        vm[cell].checksum = this.checksum
      }
    }
    else if (seamless_read_paths["json"].indexOf(path) >= 0) {
      ctx[path].onchange = function () {
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
    else if (seamless_read_paths["text"].indexOf(path) >= 0) {
      ctx[path].onchange = function () {
        vm[cell].value = this.value
        vm[cell].checksum = this.checksum
      }
    }

    if (seamless_auto_read_paths.indexOf(path) >= 0) {
      ctx[path].auto_read = true
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

function seamless_update(path, value, encoding) {
  if (!ctx) return
  if (!ctx.self.sharelist) return
  if (ctx.self.sharelist.indexOf(path) < 0) return
  if (ctx[path].binary) {
    ctx[path].set(value)
  }
  else if (encoding == "json") {
    ctx[path].set(JSON.stringify(value))
  }
  else if (encoding == "text") {
    ctx[path].set(value)
  }
}


const app = new Vue({
  vuetify: new Vuetify(),
  data() {
    return {
      ...{
        "sub__mycell": {
          "checksum": null,
          "value": 0
        },
        "structures": {
          "checksum": null,
          "value": {}
        },
        "representation": {
          "checksum": null,
          "value": {}
        }
      }, 
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
    "structures.value": function(){ load_ngl(nglviewer_1_stage,this.structures.value,this.representation.value) },
    "representation.value": function(){ load_ngl(nglviewer_1_stage,this.structures.value,this.representation.value) },
  },
  updated() {
if (typeof nglviewer_1_stage === 'undefined'){
    nglviewer_1_stage = new NGL.Stage("nglviewer_1")
}
    

  }
})

vm = app.$mount('#app')
