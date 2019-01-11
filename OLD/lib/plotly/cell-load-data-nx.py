import pandas as pd
from io import StringIO
df = pd.read_csv(StringIO(csv),header=None)
result = []
for n in range(len(df.columns)):
    result.append({"x": df[n].tolist()})
return result
