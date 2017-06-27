from math import exp
fins = []

def generate_fins_gauss(midx, width, step,
                  distance, xradius, yradius, rotation):
    result = []
    x = midx - width
    while x <= midx+ width:
        if width == 0:
            factor = 1
        else:
            sd = (x-midx)/width
            factor = exp(-sd**2/0.5)
        fin = FinCircle(
            x=x,
            ycenter=0.7,
            distance=distance,
            xradius=xradius,
            yradius=yradius * factor,
            rotation = rotation
        )
        result.append(fin)
        x += step
        if step == 0:
            break
    return result

fin_gens = FinGeneratorArray(fin_generators)
for fin_gen in fin_gens:
    for rotation in fin_gen.rotations:
        if fin_gen.xwidth:
            fins += generate_fins_gauss(
                fin_gen.x, fin_gen.xwidth, fin_gen.xstep,
                fin_gen.distance, fin_gen.xradius, fin_gen.yradius,
                rotation)
        else:
            d = fin_gen.json()
            d["rotation"] = rotation
            fin = FinCircle(d)
            fins.append(fin)
return FinCircleArray(fins)
