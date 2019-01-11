import pandas as pd
from io import StringIO
df = pd.read_csv(StringIO(csv))
x = list(df.columns)
result = []
for row in df.index:
    result.append({"x": x, "y": df.ix[row].tolist()})
return result
