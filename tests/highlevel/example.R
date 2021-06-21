addPercent <- function(x){
 percent <- round(x * 100, digits = 1)
 result <- paste(percent, "%", sep = "")
 return(result)
}

frac = a / b
result <- addPercent(frac)
