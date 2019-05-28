typedef struct Coor1Struct {
  const double *data;
  unsigned int shape[2];
} Coor1Struct;

typedef struct Coor2Struct {
  const double *data;
  unsigned int shape[2];
} Coor2Struct;

float transform(const Coor1Struct* coor1, const Coor2Struct* coor2) {
  return 0.42;
}
