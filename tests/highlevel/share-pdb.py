#!/usr/bin/env python
# coding: utf-8

# In[1]:


import seamless


# In[2]:


from seamless.highlevel import Context, Transformer

try:
    import seamless
    redis_sink = seamless.RedisSink()
    import asyncio
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.5))
    redis_sink.connection.info()
except:
    print("No Redis found!")

ctx = Context()

ctx.pdb0 = open("1crn.pdb").read()
ctx.pdb0.celltype = "text"
ctx.pdb0.share()

ctx.filter_pdb = Transformer()
ctx.filter_pdb.language = "bash"
ctx.filter_pdb.code = 'grep ATOM pdb0 | awk \'$3 == "CA" || $3 == "C" || $3 == "O" || $3 == "N"\' '
ctx.filter_pdb.pdb0 = ctx.pdb0

ctx.bb_pdb = ctx.filter_pdb
ctx.bb_pdb.celltype = "text"
ctx.bb_pdb.share()

ctx.bb_pdb = ctx.filter_pdb
ctx.bb_pdb.celltype = "text"
ctx.bb_pdb.share()

ctx.fix_pdb = Transformer()
ctx.fix_pdb.language = "bash"
ctx.fix_pdb.code = 'cat bb_pdb0'
ctx.fix_pdb.bb_pdb0 = ctx.bb_pdb

ctx.pdb = ctx.fix_pdb
ctx.pdb.celltype = "text"
ctx.pdb.share()

ctx.code >> ctx.fix_pdb.code
ctx.code.share()

graph = ctx.get_graph()
import json
json.dump(graph, open("share-pdb.seamless", "w"), indent=2, sort_keys=True)

ctx.code.mount("/tmp/code.bash")
ctx.equilibrate()


# In[4]:


ctx.code.set("tail bb_pdb0")


# In[5]:


ctx.code.value


# In[ ]:




