import copy
result = []
for n in range(len(data)):
    series = {}
    if n >= len(attrib):
        if len(attrib) > 0:
            series = attrib[-1]
    else:
        series = attrib[n]
    series = copy.deepcopy(series)
    series.update(data[n])
    result.append(series)
return result
