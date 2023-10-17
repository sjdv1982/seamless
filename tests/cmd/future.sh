rm job?.txt* -f
seamless -c -cp :job1.txt 'sleep 3 && echo 3' &
seamless -c -cp :job2.txt 'sleep 5 && echo 5' &
sleep 0.5
seamless -c -cp :job3.txt 'cat job1.txt job2.txt | awk '\''{x+=$1} END{print x}'\'
wait
cat job1.txt   # 3
cat job2.txt   # 5
cat job3.txt   # 8
seamless --undo -c -cp :job1.txt 'sleep 3 && echo 3'
seamless --undo -c -cp :job2.txt 'sleep 5 && echo 5'
seamless --undo -c -cp :job3.txt 'cat job1.txt job2.txt | awk '\''{x+=$1} END{print x}'\'
rm job?.txt* -f

