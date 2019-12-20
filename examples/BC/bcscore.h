
/*
The following C header has been auto-generated from the transformer schema
It will be used to generate bindings, but it will not be automatically
added to the compiled transformer code.

If your transformer code is written in C/C++, you may do so yourself.
For C, you may need to include "stdint.h" and "stdbool.h".
If your transform() function is written in C++, don't forget to add "extern C"
*/

typedef struct Coor1Struct {
  const double *data;
  unsigned int shape[2];
} Coor1Struct;

typedef struct Coor2Struct {
  const double *data;
  unsigned int shape[2];
} Coor2Struct;

float transform(const Coor1Struct* coor1, const Coor2Struct* coor2, int flanksize, int gapsize);
