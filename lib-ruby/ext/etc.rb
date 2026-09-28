# etc.so for topaz: the password and group databases read from
# /etc/passwd and /etc/group, and the few system facts gems ask for.
module Etc
  VERSION = "1.4.6"

  Passwd = Struct.new(:name, :passwd, :uid, :gid, :gecos, :dir, :shell)
  Group = Struct.new(:name, :passwd, :gid, :mem)

  class << self
    def getlogin
      ENV["USER"] || ENV["LOGNAME"] || getpwuid&.name
    end

    def getpwuid(uid = Process.uid)
      passwd.find { |entry| entry.uid == uid }
    end

    def getpwnam(name)
      passwd.find { |entry| entry.name == name } or
        raise ArgumentError, "can't find user for #{name}"
    end

    def getgrgid(gid = Process.gid)
      group.find { |entry| entry.gid == gid }
    end

    def getgrnam(name)
      group.find { |entry| entry.name == name } or
        raise ArgumentError, "can't find group for #{name}"
    end

    def passwd
      entries = __read("/etc/passwd").map do |fields|
        Passwd.new(fields[0], fields[1], fields[2].to_i, fields[3].to_i, fields[4], fields[5], fields[6])
      end
      return entries.each { |entry| yield entry } if block_given?
      entries
    end

    def group
      entries = __read("/etc/group").map do |fields|
        Group.new(fields[0], fields[1], fields[2].to_i, (fields[3] || "").split(","))
      end
      return entries.each { |entry| yield entry } if block_given?
      entries
    end

    def nprocessors
      count = File.read("/proc/cpuinfo").scan(/^processor\s*:/).size rescue 0
      count > 0 ? count : 1
    end

    def sysconfdir
      "/etc"
    end

    def systmpdir
      "/tmp"
    end

    def uname
      {
        sysname: __proc("ostype", "Linux"),
        nodename: __proc("hostname", "localhost"),
        release: __proc("osrelease", ""),
        version: __proc("version", ""),
        machine: RbConfig::CONFIG["host_cpu"] || "x86_64",
      }
    end

    private

    def __read(path)
      File.readlines(path, chomp: true).reject { |line| line.empty? || line.start_with?("#") }
          .map { |line| line.split(":", -1) }
    rescue SystemCallError
      []
    end

    def __proc(name, default)
      File.read("/proc/sys/kernel/#{name}").chomp
    rescue SystemCallError
      default
    end
  end
end
