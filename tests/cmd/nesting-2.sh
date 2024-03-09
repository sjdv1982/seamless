wc -c ./nesting-1.sh
seamless -c """wc -c ./nesting-1.sh; echo NEST; ./nesting-1.sh QQQ; echo /NEST"""