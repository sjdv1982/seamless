typedef double Real;
typedef Real Coord[3];
const Real EPS = 1.e-8;

#include "math.h"
#include "stdio.h"

void getCenter(const Coord X[], int len, Coord *cx) {
  Real sum;
  int i,j;
  for (i=0; i<3;i++) {
    sum=0;
    for (j=0; j<len;j++) {
      sum+=X[j][i];
    }
    (*cx)[i]=sum/len;
  }
}


inline Real det3x3(Real K[3][3]) {
  return K[0][0]*(K[1][1]*K[2][2]-K[2][1]*K[1][2])+K[1][0]*(K[2][1]*K[0][2]-K[0][1]*K[2][2])+K[2][0]*(K[0][1]*K[1][2]-K[1][1]*K[0][2]);
}

Real BC0(const Coord X[], const Coord Y[], int len) {
  Real K[3][3];
  Coord cx, cy;
  Real det, sum;
  int i,j,k;

  getCenter(X, len, &cx);
  getCenter(Y, len, &cy);
  for (i=0; i<3;i++)
    for (j=0; j<3; j++) {
      sum=0;
      for (k=0; k<len;k++)
        sum+=(Y[k][i]-cy[i])*(X[k][j]-cx[i]);
      K[i][j]=sum;
    }
  det=det3x3(K);
  return det;
}

Real BC(const Coord X[], const Coord Y[], int len) {
  Real det, detX, detY;
  det=BC0(X, Y, len);
  detX=BC0(X, X, len);
  detY=BC0(Y, Y, len);
  if (fabs(detY)<EPS ) {
    fprintf(stderr, "null determinant! len=%d\n",len);return 0.;
  }
  return det/(sqrt(detX)*sqrt(detY));
}
