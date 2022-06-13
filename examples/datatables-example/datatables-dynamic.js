
ctx = connect_seamless()
ctx.self.onsharelist = function(sharelist) {
    sharelist.forEach(element => {
        if (element.indexOf(".") != -1) {
            // explicitly ignore datatables-dynamic.html, etc.
            return
        }
        var inputElement = document.getElementById(element)
        if (inputElement === null) {
           inputElement = document.getElementsByName(element)
           inputElement = inputElement[0]
           if (inputElement === null) return
        }
        

        if (element == "datatable") {
            ctx[element].onchange = function() {                
                value = this.value
                //inputElement.innerHTML = value //does not work; need to unwrap and execute script tags
                $(inputElement).html(value) 
            }        
        }

        else {     
            ctx[element].onchange = function() {
                const v = JSON.parse(this.value)
                inputElement.value = v
                const inputElement2 = document.getElementById(element+"2")
                if (inputElement2 === null) return
                inputElement2.innerHTML = v
            }        
            inputElement.onchange = function() {
                v = this.value
                ctx[element].set(v)
                const inputElement2 = document.getElementById(element+"2")
                if (inputElement2 === null) return
                inputElement2.innerHTML = v
            }
        }
    })
} 
