# socket.so for topaz: the classes, constants and errors that code refers
# to when it is loaded. topaz has no sockets yet, so opening one raises
# NotImplementedError; Socket.gethostname and the Addrinfo basics work.
class SocketError < StandardError; end

class BasicSocket < IO
  def self.do_not_reverse_lookup
    true
  end

  def self.do_not_reverse_lookup=(value)
    value
  end

  def self.for_fd(fd)
    raise NotImplementedError, "topaz does not support sockets"
  end

  def initialize(*)
    raise NotImplementedError, "topaz does not support sockets"
  end
end

class Socket < BasicSocket
  module Constants
    AF_UNSPEC = 0
    AF_UNIX = 1
    AF_LOCAL = 1
    AF_INET = 2
    AF_INET6 = 10
    PF_UNSPEC = 0
    PF_UNIX = 1
    PF_LOCAL = 1
    PF_INET = 2
    PF_INET6 = 10
    SOCK_STREAM = 1
    SOCK_DGRAM = 2
    SOCK_RAW = 3
    SOCK_SEQPACKET = 5
    SOCK_NONBLOCK = 2048
    SOCK_CLOEXEC = 524288
    IPPROTO_IP = 0
    IPPROTO_TCP = 6
    IPPROTO_UDP = 17
    IPPROTO_IPV6 = 41
    SOL_SOCKET = 1
    SO_REUSEADDR = 2
    SO_KEEPALIVE = 9
    SO_LINGER = 13
    SO_RCVBUF = 8
    SO_SNDBUF = 7
    SO_REUSEPORT = 15
    TCP_NODELAY = 1
    TCP_KEEPIDLE = 4
    TCP_KEEPINTVL = 5
    TCP_KEEPCNT = 6
    SHUT_RD = 0
    SHUT_WR = 1
    SHUT_RDWR = 2
    MSG_PEEK = 2
    MSG_DONTWAIT = 64
    AI_PASSIVE = 1
    AI_CANONNAME = 2
    AI_NUMERICHOST = 4
    NI_NUMERICHOST = 1
    NI_NUMERICSERV = 2
    INADDR_ANY = 0
    INADDR_LOOPBACK = 0x7f000001
    SOMAXCONN = 4096
    EAI_NONAME = -2
  end
  include Constants
  Constants.constants.each { |name| const_set(name, Constants.const_get(name)) }

  class ResolutionError < SocketError
    def error_code
      Constants::EAI_NONAME
    end
  end

  def self.gethostname
    File.read("/proc/sys/kernel/hostname").chomp
  rescue SystemCallError
    ENV["HOSTNAME"] || "localhost"
  end

  def self.ip_address_list
    [Addrinfo.ip("127.0.0.1")]
  end

  def self.getaddrinfo(host, *)
    raise SocketError, "getaddrinfo: Name or service not known" unless host.nil? || host =~ /\A[\d.]+\z/ || host == "localhost"
    [["AF_INET", 0, host == "localhost" || host.nil? ? "127.0.0.1" : host, host == "localhost" || host.nil? ? "127.0.0.1" : host, AF_INET, SOCK_STREAM, IPPROTO_TCP]]
  end

  def self.tcp(*)
    raise NotImplementedError, "topaz does not support sockets"
  end

  def self.unix(*)
    raise NotImplementedError, "topaz does not support sockets"
  end

  def self.pack_sockaddr_in(port, host)
    [AF_INET, port.to_i, host.to_s].pack("SnA*")
  end

  def self.sockaddr_in(port, host)
    pack_sockaddr_in(port, host)
  end
end

class IPSocket < BasicSocket
  def self.getaddress(host)
    return "127.0.0.1" if host == "localhost"
    return host if host =~ /\A[\d.]+\z/ || host.include?(":")
    raise SocketError, "getaddrinfo: Name or service not known"
  end
end

class TCPSocket < IPSocket
  def self.gethostbyname(host)
    [host, [], Socket::AF_INET, IPSocket.getaddress(host)]
  end
end

class TCPServer < TCPSocket; end
class UDPSocket < IPSocket; end
class UNIXSocket < BasicSocket; end
class UNIXServer < UNIXSocket; end

class Addrinfo
  attr_reader :afamily, :pfamily, :socktype, :protocol

  def self.ip(host)
    new(host, 0)
  end

  def self.tcp(host, port)
    new(host, port, Socket::SOCK_STREAM)
  end

  def self.udp(host, port)
    new(host, port, Socket::SOCK_DGRAM)
  end

  def self.getaddrinfo(host, port = nil, *)
    [tcp(IPSocket.getaddress(host), port.to_i)]
  end

  def initialize(host, port = 0, socktype = 0)
    @host = host
    @port = port
    @socktype = socktype
    @afamily = host.to_s.include?(":") ? Socket::AF_INET6 : Socket::AF_INET
    @pfamily = @afamily
    @protocol = 0
  end

  def ip_address
    @host
  end

  def ip_port
    @port
  end

  def ip?
    true
  end

  def ipv4?
    @afamily == Socket::AF_INET
  end

  def ipv6?
    @afamily == Socket::AF_INET6
  end

  def ipv4_loopback?
    @host.to_s.start_with?("127.")
  end

  def ipv6_loopback?
    @host == "::1"
  end

  def ipv4_private?
    @host.to_s.match?(/\A(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/)
  end

  def unix?
    false
  end

  def inspect_sockaddr
    ipv6? ? "[#{@host}]:#{@port}" : "#{@host}:#{@port}"
  end

  def inspect
    "#<Addrinfo: #{inspect_sockaddr}>"
  end
end
