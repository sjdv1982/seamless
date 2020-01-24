fetch("./script.js")
.then(function(response) {
    return response.text()
})    
.then(function(code) {
    document.getElementById("test").innerHTML = "<pre>" + code + "</pre>"
})    
