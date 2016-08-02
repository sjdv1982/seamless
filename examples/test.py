import matplotlib.pyplot as plt
plt.close('all')
import numpy as np
from io import StringIO
f = StringIO()

t = np.arange(0.0, 2.0, 0.01)
s = np.sin(2*np.pi*t)
plt.plot(t, s)
plt.xlabel('time (s)')
plt.ylabel('voltage (mV)')
plt.title('About as simple as it gets, folks')
plt.grid(True)
plt.savefig(f, format="svg")

print(f.getvalue())
