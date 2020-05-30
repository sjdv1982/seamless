#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>

typedef struct Atoms1Struct {
  const double *data;
  unsigned int shape[2];
} Atoms1Struct;

typedef struct Atoms2Struct {
  const double *data;
  unsigned int shape[2];
} Atoms2Struct;

typedef struct DbcaStruct {
  const double *data;
  unsigned int shape[2];
} DbcaStruct;

typedef struct PdbIndexStruct {
  const uint32_t *data;
  unsigned int shape[2];
} PdbIndexStruct;

typedef struct SegIndexStruct {
  const uint32_t *data;
  unsigned int shape[2];
} SegIndexStruct;

typedef struct ResultHitsStruct {
  uint32_t *data;
  unsigned int shape[2];
} ResultHitsStruct;

typedef struct ResultHitstatsStruct {
  float *data;
  unsigned int shape[2];
} ResultHitstatsStruct;

typedef struct ResultStruct {
  ResultHitsStruct *hits;
  ResultHitstatsStruct *hitstats;
  int nhits;
} ResultStruct;

int transform(const Atoms1Struct* atoms1, const Atoms2Struct* atoms2, const DbcaStruct* dbca, int looplength, int maxR, int maxloopgap, double minBC, int minloopmatch, bool mirror, const PdbIndexStruct* pdb_index, const SegIndexStruct* seg_index, ResultStruct *result);

typedef double Real;
typedef Real Coord[3];

extern int BCLoopSearch (const Coord *atoms1, int nr_atoms1, const Coord *atoms2, int nr_atoms2,  //flank1 and flank2
                  int looplength, //size of the gap/loop we are searching
                  int minloopmatch, int maxloopgap, //for partial matches: minimum total length, maximum gap
                  int mirror, //looking for mirrors?
                  float minBC, float maxR, //minimum BC score, maximum rigidity
                  const Coord *dbca, //CA database
                  int seg_index[][3], //(dbca offset, segment resnr, segment length)
                  int pdb_index[][2], int nr_pdbindex, //(seg_index offset, number of segments), total number of PDBs
                  int hits[][3], //pdbindex line, seg_index line, segment offset
                  float hitstats[][2] //score, rigidity
                 );

typedef int SegIndex[3];
typedef int PdbIndex[2];
typedef int HitIndex[3];
typedef float HitStatIndex[2];

int transform(const Atoms1Struct* atoms1, const Atoms2Struct* atoms2, const DbcaStruct* dbca, int looplength, int maxR, int maxloopgap, double minBC, int minloopmatch, bool mirror, const PdbIndexStruct* pdb_index, const SegIndexStruct* seg_index, ResultStruct *result) {
    fprintf(stderr, "BCLoopSearch C function runs!!\n");
    int nhits = BCLoopSearch (
        (const Coord *) atoms1->data, atoms1->shape[0],
        (const Coord *) atoms2->data, atoms2->shape[0],
        looplength, minloopmatch, maxloopgap, mirror,
        minBC, maxR,
        (Coord *) dbca->data,
        (SegIndex *) seg_index->data,
        (PdbIndex *) pdb_index->data, pdb_index->shape[0],
        (HitIndex *) result->hits->data,
        (HitStatIndex *) result->hitstats->data
    );

    fprintf(stderr, "NHITS %d\n", nhits);
    result->nhits = nhits;
    return 0;
}
