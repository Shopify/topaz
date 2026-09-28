# Numeric escapes in regexps: octal escapes and backreferences.
p("ab\0cd" =~ /\0/)
p("a\nb" =~ /\012/)
p("abab" =~ /(ab)\1/)
p("xAa" =~ /(a)\1/i)
p("x\x01y" =~ /[\1]/)
p("'hi'" =~ /(['"])hi\1/)
p("ab  \0".sub(/[ \0]+\z/, ""))
p("aa-bb" =~ /(a)(a)-(b)\3/)
