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
