#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>

typedef struct Atoms1Struct {
  const double *data;
  unsigned int shape[2];
  unsigned int strides[2];
} Atoms1Struct;

typedef struct Atoms2Struct {
  const double *data;
  unsigned int shape[2];
  unsigned int strides[2];
} Atoms2Struct;

typedef struct DbcaStruct {
  const double *data;
  unsigned int shape[2];
  unsigned int strides[2];
} DbcaStruct;

typedef struct PdbIndexStruct {
  const uint32_t *data;
  unsigned int shape[2];
  unsigned int strides[2];
} PdbIndexStruct;

typedef struct SegIndexStruct {
  const uint32_t *data;
  unsigned int shape[2];
  unsigned int strides[2];
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

void transform(const Atoms1Struct* atoms1, const Atoms2Struct* atoms2, const DbcaStruct* dbca, int looplength, int maxR, int maxloopgap, double minBC, int minloopmatch, bool mirror, const PdbIndexStruct* pdb_index, const SegIndexStruct* seg_index, ResultStruct *result){
    fprintf(stderr, "BCLoopSearch C function runs!\n");
    result->nhits = 42;    
    return; 
}
