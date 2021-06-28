async def main():
    #!/usr/bin/env python
    # coding: utf-8

    # In[1]:


    from seamless.highlevel import Context, Transformer, Cell
    import numpy as np

    ctx = Context()


    # In[2]:


    ctx.pdb1 = open("1AKE-flanks.pdb").read()
    ctx.pdb2 = open("1AKE-B-hit.pdb").read()
    ctx.load_pdb1 = Transformer()
    ctx.load_pdb1.pdb = ctx.pdb1
    ctx.load_pdb_code = ctx.load_pdb1.code.pull()
    ctx.load_pdb_code.mount("load_pdb.py")
    ctx.flanks = ctx.load_pdb1

    ctx.load_pdb2 = Transformer()
    ctx.load_pdb2.pdb = ctx.pdb2
    ctx.load_pdb2.code = ctx.load_pdb_code
    ctx.dbca = ctx.load_pdb2

    ctx.get_flank1 = lambda flanks: flanks[:4]
    ctx.get_flank1.flanks = ctx.flanks
    ctx.flank1 = ctx.get_flank1

    ctx.get_flank2 = lambda flanks: flanks[-4:]
    ctx.get_flank2.flanks = ctx.flanks
    ctx.flank2 = ctx.get_flank2

    await ctx.computation()
    print(ctx.flank1.value)
    print(ctx.flank2.value)


    # ```
    # int BCLoopSearch (const Coord *atoms1, int nr_atoms1, const Coord *atoms2, int nr_atoms2,  //flank1 and flank2
    #                   int looplength, //size of the gap/loop we are searching
    #                   int minloopmatch, int maxloopgap, //for partial matches: minimum total length, maximum gap
    #                   int mirror, //looking for mirrors?
    #                   float minBC, float maxR, //minimum BC score, maximum rigidity
    #                   const Coord *dbca, //CA database
    #                   int seg_index[][3], //(dbca offset, segment resnr, segment length)
    #                   int pdb_index[][2], int nr_pdbindex, //(seg_index offset, number of segments), total number of PDBs
    #                   int hits[][3], //pdbindex line, seg_index line, segment offset
    #                   float hitstats[][2] //score, rigidity
    #                  )
    # {
    # ```

    # In[3]:


    ctx.bcloopsearch = Transformer()
    ctx.bcloopsearch.language = "c"
    ctx.bcloopsearch.main_module.compiler_verbose = False
    ctx.bcloopsearch.code.mount("bcloopsearch.c", authority="file")
    ctx.bcloopsearch.main_module.lib.language = "c"
    ctx.bclib_code = ctx.bcloopsearch.main_module.lib.code.pull()
    ctx.bclib_code.mount("BCLoopSearch-lib.c", authority="file")

    ctx.bc_hits = ctx.bcloopsearch
    await ctx.translation()
    await ctx.computation()
    print(1, ctx.status, "\n")

    # In[4]:


    def set_example(bc):
        bc.atoms1 = np.zeros((4, 3))
        bc.atoms2 = np.zeros((4, 3))
        bc.looplength = 5
        bc.minloopmatch = 5
        bc.maxloopgap = 0
        bc.mirror = False
        bc.minBC = 0.9
        bc.maxR = 9999
        bc.dbca = np.zeros((10, 3))
        bc.seg_index = np.zeros((10,3), dtype=np.uint32)
        bc.pdb_index = np.zeros((10,2), dtype=np.uint32)

    set_example(ctx.bcloopsearch.example)

    schema = ctx.bcloopsearch.schema
    schema.properties.atoms1["form"].contiguous = True
    schema.properties.atoms1["form"].shape = (-1, 3)
    schema.properties.atoms2["form"].contiguous = True
    schema.properties.atoms2["form"].shape = (-1, 3)
    schema.properties.dbca["form"].shape = (-1, 3)
    schema.properties.dbca["form"].contiguous = True
    schema.properties.seg_index["form"].shape = (-1, 3)
    schema.properties.seg_index["form"].contiguous = True
    schema.properties.pdb_index["form"].shape = (-1, 2)
    schema.properties.pdb_index["form"].contiguous = True

    MAXHITS = 100000
    bcrx = ctx.bcloopsearch.result.example
    bcrx.nhits = 0
    bcrx.hits = np.zeros((MAXHITS,3), dtype=np.uint32)
    bcrx.hitstats = np.zeros((MAXHITS,2), dtype=np.float32)
    await ctx.computation()
    print(2, ctx.status, "\n")
    #print(ctx.bcloopsearch.exception); print()

    rschema = ctx.bcloopsearch.result.schema
    rschema.properties.hits["form"].shape = (MAXHITS, 3)
    rschema.properties.hitstats["form"].shape = (MAXHITS, 2)
    await ctx.computation()
    print(3, ctx.status, "\n")
    #print(ctx.bcloopsearch.exception); print()

    # In[5]:
    
    set_example(ctx.bcloopsearch)
    ctx.bcloopsearch.atoms1 = ctx.flank1
    ctx.bcloopsearch.atoms2 = ctx.flank2
    ctx.bcloopsearch.dbca = ctx.dbca
    await ctx.computation()
    ctx.bcloopsearch.seg_index = np.array([[0,1,len(ctx.dbca.value)]],dtype=np.uint32)
    ctx.bcloopsearch.pdb_index = np.array([[0,1]],dtype=np.uint32)
    ctx.bcloopsearch.looplength = 7
    ctx.bcloopsearch.minBC = 0
    await ctx.computation()    


    # In[6]:


    print(ctx.bcloopsearch.schema)
    print()
    print(ctx.bcloopsearch.result.schema)
    print()
    print(ctx.bcloopsearch.status)
    print(ctx.bcloopsearch.exception)

    # In[7]:


    ctx.header = ctx.bcloopsearch.header
    ctx.header.mimetype = "h"
    ctx.header.output

    # In[8]:


    ctx.bcloopsearch_schema = Cell()
    ctx.bcloopsearch_schema.celltype = "plain"
    ctx.link(ctx.bcloopsearch_schema, ctx.bcloopsearch.inp.schema)
    ctx.bcloopsearch_schema.mount("bcloopsearch-schema.json")
    await ctx.computation()


    # In[9]:


    ctx.bc_hits.value


    # In[10]:


    nhits = ctx.bc_hits.value.nhits
    print(nhits)


    # In[ ]:


    ctx.bc_hits.value.unsilk["hitstats"][:nhits]


    # In[ ]:


    ctx.pdb2.set(open("1AKE-B.pdb").read())
    await ctx.computation()
    ctx.bcloopsearch.seg_index= np.array([[0,1,len(ctx.dbca.value)]],dtype=np.uint32)
    await ctx.computation()
    ctx.bcloopsearch.minBC = 0.7
    await ctx.computation()


    # In[ ]:


    nhits = ctx.bc_hits.value.nhits
    print(nhits)


    # In[ ]:


    ctx.bc_hits.value.unsilk["hitstats"][:nhits]

    # In[ ]:


    dbca = np.load("db/scop-g.npy")[:, 1].astype(np.float64)
    ctx.load_db_index = lambda pdbindex, segindex: None
    ctx.load_db_index.pdbindex = open("db/scop-g.pdbindex").read()
    ctx.load_db_index.segindex = open("db/scop-g.segindex").read()
    ctx.load_db_index.code.mount("load_db_index.py", authority="file")
    ctx.db_index = ctx.load_db_index
    del ctx.dbca
    ctx.dbca = dbca
    ctx.bcloopsearch.dbca = ctx.dbca
    ctx.bcloopsearch.seg_index = ctx.db_index.seg
    ctx.bcloopsearch.pdb_index = ctx.db_index.pdb
    ctx.bcloopsearch.minBC = 0.99
    await ctx.computation()


    # In[ ]:


    nhits = ctx.bc_hits.value.nhits
    print(nhits)


    # In[ ]:


    pdbs = ctx.bc_hits.value.unsilk["hits"][:nhits,0]
    print(np.take(ctx.db_index.value.unsilk["pdb_names"], pdbs))
    print(ctx.bc_hits.value.unsilk["hits"][:nhits,1])
    print(ctx.bc_hits.value.unsilk["hits"][:nhits,2])
    print(ctx.bc_hits.value.unsilk["hitstats"][:nhits])

import asyncio
asyncio.run(main())