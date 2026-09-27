Each script here prints the results of exercising some Ruby 2.x-4.0
feature; the `.expected` file next to it is what CRuby 4.0.6 printed.
`run.sh` runs them with a translated `bin/topaz` and reports any
difference. To add one, write the script and record CRuby's output:

    ruby foo.rb > foo.expected 2>&1
