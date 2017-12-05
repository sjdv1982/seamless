import numpy as np

class Test:
    z = [1,2,3]
    def __len__(self):
        return len(self.z)
    def __iter__(self):
        return iter(self.z)
    def __getitem__(self, item):
        print("ITEM", item)
        return self.z[item]

t = Test()
a = np.array(t)
print(a, type(a), a.shape)


from silk import Silk
s = Silk().set([10,20,30])
aa = np.array(s)
print(aa, type(aa), aa.shape)
print(s[:2])
