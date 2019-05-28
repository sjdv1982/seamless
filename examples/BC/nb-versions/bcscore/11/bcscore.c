typedef struct Coor1Struct {
  const double *data;
  unsigned int shape[2];
} Coor1Struct;

typedef struct Coor2Struct {
  const double *data;
  unsigned int shape[2];
} Coor2Struct;

typedef double Real;
typedef Real Coord[3];

extern Real BC(const Coord X[], const Coord Y[], int len);

float transform(const Coor1Struct* coor1, const Coor2Struct* coor2, int flanksize, int gapsize) {
  Coord *c1 = (Coord *) coor1->data;
  Coord *c2 = (Coord *) coor2->data;
  int len = coor1->shape[0];
  return BC(c1, c2, len);  
}
