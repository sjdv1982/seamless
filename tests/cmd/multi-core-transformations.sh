rm -f tf tf2
trap 'kill -1 $(jobs -p); kill $(jobs -p); kill -9 $(jobs -p)' EXIT
random=$RANDOM
seamless --direct-print --ncores 5 -c \
  "python multi-core-transformations.py 1 5 $random > tf" & 
t1=$!
sleep 0.5
random=$RANDOM
seamless --direct-print --ncores 1 -c \
  "python multi-core-transformations.py 2 2 $random > tf2" & 
t2=$!
start=$SECONDS
wait $t2
echo "$(($SECONDS - $start)) seconds have passed"
echo "Job 1" $(cat tf)  # file will only exist if the assistant has ncores=6 or higher
echo "Job 2" $(cat tf2)
wait $t1
echo "Job 1" $(cat tf)
rm -f tf tf.CHECKSUM tf2 tf2.CHECKSUM