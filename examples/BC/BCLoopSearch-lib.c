/*
 * Adaptation of BCLoopSearch (routines in BCscore3_PT.c) by Sjoerd de Vries, MTi, 2016
 *
 * BCLoopSearch/BCSearch/BCScore author: Frederic Guyon, MTi
 * Citations:
 *      Fast protein fragment similarity scoring using a Binet-Cauchy Kernel, Bioinformatics, Frederic Guyon  and Pierre Tuffery,  doi:10.1093/bioinformatics/btt618
 *
 *
 * gcc -shared -o BCLoopSearchlib.so BCLoopSearch.c -fPIC -O3 -lm
*/

#include "stdio.h"
#include "math.h"
#include "memory.h"

typedef double Real; //TODO: test single precision?
typedef Real Coord[3];
const Real EPS = 1.e-8;
const int NMAX = 5000;
const int MAXHITS = 100000;
#define min(a,b) (a<b?a:b)
#define max(a,b) (a<b?b:a)


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


Real det3x3(Real K[3][3]) {
  return K[0][0]*(K[1][1]*K[2][2]-K[2][1]*K[1][2])+K[1][0]*(K[2][1]*K[0][2]-K[0][1]*K[2][2])+K[2][0]*(K[0][1]*K[1][2]-K[1][1]*K[0][2]);
}

Real BC(const Coord X[], const Coord Y[], int len) {
  //assumes that X (but not Y) has been centered
  Real K[3][3], cy[3];
  Real det, sum;
  int i,j,k;

  getCenter(Y, len, &cy);
  for (i=0; i<3;i++)
    for (j=0; j<3; j++) {
      sum=0;
      for (k=0; k<len;k++)
        sum+=(Y[k][i]-cy[i])*X[k][j];
      K[i][j]=sum;
    }
  det=det3x3(K);
  return det;
}

Real NBC(const Coord X[], const Coord Y[], int len, Real sqdetX) {
  Real det, detY;
  det=BC(X, Y, len);
  detY=BC(Y, Y, len);
  if (fabs(detY)<EPS ) {
    fprintf(stderr, "null determinant! len=%d\n",len);return 0.;
  }
  return det/(sqdetX*sqrt(detY));
}


Real dist2(const Real *X,  const Real *Y) {
  Real x, sum;
  int k;
  sum=0;
  for (k=0; k<3;k++) {
    x=X[k]-Y[k];
    sum+=x*x;
  }
  // Faster not to get sqrt
  sum=sqrt(sum);
  return sum;
}

Real rigidity(const Coord X[], const Coord Y[], int len) {
  Coord Xm, Ym;
  Real sum1, sum2, sum;
  int i;

  getCenter(X,len, &Xm);
  getCenter(Y,len, &Ym);
  sum=0;
  for (i=0;i<len;i++) {
    sum1=dist2(Xm, X[i]);
    sum2=dist2(Ym, Y[i]);
    sum=max(sum,fabs((sum1-sum2)/(sum1+sum2)));
  }
  sum1=dist2(X[0], X[len-1]);
  sum2=dist2(Y[0], Y[len-1]);
  // sum=max(sum,fabs((sum1-sum2)/(sum1+sum2)));
  sum=max(sum,fabs((sum1-sum2)));
  return sum;
}

int BCLoopSearch (const Coord *atoms1, int nr_atoms1, const Coord *atoms2, int nr_atoms2,  //flank1 and flank2
                  int looplength, //size of the gap/loop we are searching
                  int minloopmatch, int maxloopgap, //for partial matches: minimum total length, maximum gap
                  int mirror, //looking for mirrors?
                  float minBC, float maxR, //minimum BC score, maximum rigidity
                  const Coord *dbca, //CA database
                  int seg_index[][3], //(dbca offset, segment resnr, segment length)
                  int pdb_index[][2], int nr_pdbindex, //(seg_index offset, number of segments), total number of PDBs
                  int hits[][3], //pdbindex line, seg_index line, segment offset
                  float hitstats[][2] //score, rigidity
                 )
{
  Coord X[NMAX];
  Coord Y[NMAX];
  int nX = nr_atoms1 + nr_atoms2;
  if (nX > NMAX) {
    fprintf(stderr, "NMAX exceeded! len=%d\n",nX); return -1;
  }
  memcpy(X,             atoms1, nr_atoms1 * sizeof(Coord));
  memcpy(X + nr_atoms1, atoms2, nr_atoms2 * sizeof(Coord));
  Coord cx;
  getCenter(X, nX, &cx);
  int n1, n2;
  for (n1 = 0; n1 < nX; n1++) {
    for (n2 = 0; n2 < 3; n2++) {
      X[n1][n2] -= cx[n2];
    }
  }
  Real detX = BC(X, X, nX);
  if (fabs(detX)<EPS ) {
    fprintf(stderr, "null determinant! len=%d\n",nX);return -1;
  }
  Real sqdetX = sqrt(detX);
  int totlength = nr_atoms1 + looplength + nr_atoms2;
  int pdb, seg1, seg2;
  int nhits = 0;
  for (pdb = 0; pdb < nr_pdbindex; pdb++) {
    int seg_offset = pdb_index[pdb][0];
    int nsegs = pdb_index[pdb][1];
    for (seg1 = seg_offset; seg1 < seg_offset + nsegs; seg1++) {
      int dbca_offset1 = seg_index[seg1][0];
      int seg1_first_resnr = seg_index[seg1][1];
      int seglen1 = seg_index[seg1][2];
      const Coord *dbca_seg1 = &dbca[dbca_offset1];
      for (n1 = 0; n1 < seglen1; n1++) {
        if (n1 + nr_atoms1 >= seglen1) continue;
        if (seglen1 - n1 - totlength >= 0) {
          //flank1, loop and flank2 all on the same segment
          memcpy(Y,             dbca_seg1 + n1,                          nr_atoms1 * sizeof(Coord));
          memcpy(Y + nr_atoms1, dbca_seg1 + n1 + nr_atoms1 + looplength, nr_atoms2 * sizeof(Coord));
          //printf("%d\n", 0);
        }
        else if (seglen1 - n1 - nr_atoms1 - looplength >= 0) {
          //segment 1 border inside flank2 region; won't work
          continue;
        }
        else { //at least part of the gap is beyond segment 1
          int loopnonmatch = 0;
          int seg1_last_resnr = seg1_first_resnr + seglen1 - 1;
          int seg2 = seg1 + 1;
          if (seg2 - seg_offset == nsegs) {
            //last segment of this PDB; won't work
            continue;
          }
          int dbca_offset2 = seg_index[seg2][0];
          int seg2_first_resnr = seg_index[seg2][1];
          int seglen2 = seg_index[seg2][2];
          int inter_segment_gap = seg2_first_resnr - seg1_last_resnr - 1;
          if (inter_segment_gap > maxloopgap) {
            //gap too big between segments
            continue;
          }
          loopnonmatch += inter_segment_gap;
          int restgap = looplength - (seglen1 - n1 - nr_atoms1) - inter_segment_gap;
          if (restgap < 0) {
            //flank2 starts between segments; won't work
            continue;
          }
          if (seglen2 < restgap) {
            //very small segment inside the gap; let's take another one
            int seg2_old_last_resnr = seg2_first_resnr + seglen2 - 1;
            seg2 = seg2 + 1;
            if (seg2 - seg_offset == nsegs) {
              //last segment of this PDB; won't work
              continue;
            }
            dbca_offset2 = seg_index[seg2][0];
            seg2_first_resnr = seg_index[seg2][1];
            inter_segment_gap = seg2_first_resnr - seg2_old_last_resnr - 1;
            if (inter_segment_gap > maxloopgap) {
              //gap too big between segments
              continue;
            }
            loopnonmatch += inter_segment_gap;
            restgap = restgap - seglen2 - inter_segment_gap;
            seglen2 = seg_index[seg2][2];
            if (restgap < 0) {
              //flank2 starts between segments; won't work
              continue;
            }
            if (seglen2 < restgap) {
              //another very small segment inside the gap; give up
              continue;
            }
          }
          n2 = restgap;
          if (n2 +  nr_atoms2 > seglen2) {
            //flank2 does not fit in the rest of segment 2; won't work
            continue;
          }
          if (looplength - loopnonmatch <  minloopmatch) {
            //we didn't match enough of the loop
            continue;
          }
          const Coord *dbca_seg2 = &dbca[dbca_offset2];
          memcpy(Y,             dbca_seg1 + n1, nr_atoms1 * sizeof(Coord));
          memcpy(Y + nr_atoms1, dbca_seg2 + n2, nr_atoms2 * sizeof(Coord));
        }

        //OK, we got our X and Y coordinate arrays... is the match any good?
        float score0 = NBC(X, Y, nX, sqdetX);
        if ((!mirror) && (score0 <minBC)) continue;
        if (mirror && (score0 >-minBC)) continue;
        float rigid=rigidity(X,Y,nX);
        if (rigid>maxR) continue;
        //pdbindex line, seg_index line, segment offset
        hits[nhits][0] = pdb;
        hits[nhits][1] = seg1;
        hits[nhits][2] = n1;
        hitstats[nhits][0] = score0;
        hitstats[nhits][1] = rigid;
        nhits++;
        if (nhits == MAXHITS) {
          fprintf(stderr, "MAXHITS reached!"); return MAXHITS;
        }
      }
    }
  }
  return nhits;
}
