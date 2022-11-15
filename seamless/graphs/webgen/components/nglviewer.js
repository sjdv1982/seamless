ngl_stages = {}

function load_ngl(stage_id, pdbs, representations){
    if (Object.keys(pdbs).length === 0) return;

    var stage = ngl_stages[stage_id]
    if (typeof stage === 'null' || typeof stage === 'undefined'){
        var stage = new NGL.Stage(stage_id)
        ngl_stages[stage_id] = stage
    }
    stage.removeAllComponents()
    var pdbs2 = pdbs
    if (typeof pdbs === "string") {
        var pdbs2 = {"DEFAULT": pdbs}
    }
    Object.keys(pdbs2).forEach(function(item){
        let pdb = new Blob([pdbs2[item]], {type : 'text/plain'})
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
