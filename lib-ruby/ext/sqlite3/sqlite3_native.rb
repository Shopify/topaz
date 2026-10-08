# The C half of the sqlite3 gem (sqlite3/sqlite3_native.so) on libsqlite3
# through FFI: SQLite3::Database's and SQLite3::Statement's native
# methods, the Open constants and SQLite3's module functions. The gem's
# Ruby files (database.rb, statement.rb, ...) run unchanged on top.
#
# Not supported, since topaz's FFI has no callbacks yet: user-defined
# SQL functions and aggregates, trace, authorizer and collations.
# busy_handler keeps its block but waits with sqlite3_busy_timeout.
require "ffi"
require "topaz/native_library"

module SQLite3
  module LibSQLite
    extend FFI::Library

    Topaz::NativeLibrary.load(self, "libsqlite3", env: "TOPAZ_LIBSQLITE3", names: ["libsqlite3.so.0", "libsqlite3.so", "sqlite3"])

    attach_function :sqlite3_libversion, [], :string
    attach_function :sqlite3_libversion_number, [], :int
    attach_function :sqlite3_threadsafe, [], :int
    attach_function :sqlite3_open_v2, [:string, :pointer, :int, :pointer], :int
    attach_function :sqlite3_close_v2, [:pointer], :int
    attach_function :sqlite3_errmsg, [:pointer], :string
    attach_function :sqlite3_errcode, [:pointer], :int
    attach_function :sqlite3_errstr, [:int], :string
    attach_function :sqlite3_error_offset, [:pointer], :int
    attach_function :sqlite3_extended_result_codes, [:pointer, :int], :int
    attach_function :sqlite3_changes, [:pointer], :int
    attach_function :sqlite3_total_changes, [:pointer], :int
    attach_function :sqlite3_last_insert_rowid, [:pointer], :int64
    attach_function :sqlite3_busy_timeout, [:pointer, :int], :int
    attach_function :sqlite3_get_autocommit, [:pointer], :int
    attach_function :sqlite3_interrupt, [:pointer], :void
    attach_function :sqlite3_complete, [:string], :int
    attach_function :sqlite3_db_filename, [:pointer, :string], :pointer
    attach_function :sqlite3_enable_load_extension, [:pointer, :int], :int
    attach_function :sqlite3_load_extension, [:pointer, :string, :pointer, :pointer], :int
    attach_function :sqlite3_prepare_v2, [:pointer, :pointer, :int, :pointer, :pointer], :int
    attach_function :sqlite3_finalize, [:pointer], :int
    attach_function :sqlite3_step, [:pointer], :int
    attach_function :sqlite3_reset, [:pointer], :int
    attach_function :sqlite3_clear_bindings, [:pointer], :int
    attach_function :sqlite3_column_count, [:pointer], :int
    attach_function :sqlite3_column_type, [:pointer, :int], :int
    attach_function :sqlite3_column_int64, [:pointer, :int], :int64
    attach_function :sqlite3_column_double, [:pointer, :int], :double
    attach_function :sqlite3_column_text, [:pointer, :int], :pointer
    attach_function :sqlite3_column_blob, [:pointer, :int], :pointer
    attach_function :sqlite3_column_bytes, [:pointer, :int], :int
    attach_function :sqlite3_column_name, [:pointer, :int], :string
    attach_function :sqlite3_column_decltype, [:pointer, :int], :pointer
    attach_function :sqlite3_column_database_name, [:pointer, :int], :pointer
    attach_function :sqlite3_bind_parameter_count, [:pointer], :int
    attach_function :sqlite3_bind_parameter_index, [:pointer, :string], :int
    attach_function :sqlite3_bind_int64, [:pointer, :int, :int64], :int
    attach_function :sqlite3_bind_double, [:pointer, :int, :double], :int
    attach_function :sqlite3_bind_null, [:pointer, :int], :int
    attach_function :sqlite3_bind_text, [:pointer, :int, :pointer, :int, :pointer], :int
    attach_function :sqlite3_bind_blob, [:pointer, :int, :pointer, :int, :pointer], :int
    attach_function :sqlite3_sql, [:pointer], :string
    attach_function :sqlite3_expanded_sql, [:pointer], :pointer
    attach_function :sqlite3_free, [:pointer], :void
    attach_function :sqlite3_stmt_status, [:pointer, :int, :int], :int
    attach_function :sqlite3_status64, [:int, :pointer, :pointer, :int], :int
    attach_function :sqlite3_backup_init, [:pointer, :string, :pointer, :string], :pointer
    attach_function :sqlite3_backup_step, [:pointer, :int], :int
    attach_function :sqlite3_backup_finish, [:pointer], :int
    attach_function :sqlite3_backup_remaining, [:pointer], :int
    attach_function :sqlite3_backup_pagecount, [:pointer], :int

    OK = 0
    ROW = 100
    DONE = 101
    INTEGER = 1
    FLOAT = 2
    TEXT = 3
    BLOB = 4
    NULL = 5
    # SQLITE_TRANSIENT: sqlite copies bound values.
    TRANSIENT = FFI::Pointer.new(-1)

    def self.buffer(string)
      memory = FFI::MemoryPointer.new(:char, string.bytesize + 1)
      memory.put_bytes(0, string, 0, string.bytesize) if string.bytesize > 0
      memory
    end

    def self.string_at(pointer)
      pointer.null? ? nil : pointer.get_string(0)
    end
  end

  SQLITE_VERSION = LibSQLite.sqlite3_libversion
  SQLITE_VERSION_NUMBER = LibSQLite.sqlite3_libversion_number
  SQLITE_LOADED_VERSION = SQLITE_VERSION
  SQLITE_PACKAGED_LIBRARIES = false
  SQLITE_PRECOMPILED_LIBRARIES = false

  module Constants
    module Open
      READONLY = 0x00000001
      READWRITE = 0x00000002
      CREATE = 0x00000004
      DELETEONCLOSE = 0x00000008
      EXCLUSIVE = 0x00000010
      AUTOPROXY = 0x00000020
      URI = 0x00000040
      MEMORY = 0x00000080
      MAIN_DB = 0x00000100
      TEMP_DB = 0x00000200
      TRANSIENT_DB = 0x00000400
      MAIN_JOURNAL = 0x00000800
      TEMP_JOURNAL = 0x00001000
      SUBJOURNAL = 0x00002000
      MASTER_JOURNAL = 0x00004000
      SUPER_JOURNAL = 0x00004000
      NOMUTEX = 0x00008000
      FULLMUTEX = 0x00010000
      SHAREDCACHE = 0x00020000
      PRIVATECACHE = 0x00040000
      WAL = 0x00080000
    end
  end

  ERROR_CLASSES = {
    1 => "SQLException", 2 => "InternalException", 3 => "PermissionException",
    4 => "AbortException", 5 => "BusyException", 6 => "LockedException",
    7 => "MemoryException", 8 => "ReadOnlyException", 9 => "InterruptException",
    10 => "IOException", 11 => "CorruptException", 12 => "NotFoundException",
    13 => "FullException", 14 => "CantOpenException", 15 => "ProtocolException",
    16 => "EmptyException", 17 => "SchemaChangedException", 18 => "TooBigException",
    19 => "ConstraintException", 20 => "MismatchException", 21 => "MisuseException",
    22 => "UnsupportedException", 23 => "AuthorizationException", 24 => "FormatException",
    25 => "RangeException", 26 => "NotADatabaseException",
  }.freeze

  # Raises the exception for a result code, with the connection's message.
  def self.__raise(db, status, sql = nil, message = nil)
    return if status == LibSQLite::OK
    name = ERROR_CLASSES[status & 0xff]
    klass = name ? SQLite3.const_get(name) : SQLite3::Exception
    message ||= db && !db.null? ? LibSQLite.sqlite3_errmsg(db) : LibSQLite.sqlite3_errstr(status)
    error = klass.new(message)
    error.instance_variable_set(:@code, status)
    if sql
      error.instance_variable_set(:@sql, sql)
      error.instance_variable_set(:@sql_offset, db && !db.null? ? LibSQLite.sqlite3_error_offset(db) : -1)
    end
    raise error
  end

  def self.libversion
    SQLITE_VERSION_NUMBER
  end

  def self.sqlcipher?
    false
  end

  def self.threadsafe
    LibSQLite.sqlite3_threadsafe
  end

  def self.status(parameter, reset_flag = false)
    current = FFI::MemoryPointer.new(:int64, 1)
    highwater = FFI::MemoryPointer.new(:int64, 1)
    LibSQLite.sqlite3_status64(parameter, current, highwater, reset_flag ? 1 : 0)
    { current: current.get_int64(0), highwater: highwater.get_int64(0) }
  end

  class Blob < String; end

  class Database
    def self.open16(file)
      raise NotImplementedError, "UTF-16 file names are not supported by topaz's sqlite3"
    end

    # The sqlite3* of this connection.
    def __topaz_db
      raise SQLite3::Exception, "cannot use a closed database" if @__topaz_db.nil?
      @__topaz_db
    end

    def closed?
      @__topaz_db.nil?
    end

    def close
      db = @__topaz_db
      return self if db.nil?
      status = LibSQLite.sqlite3_close_v2(db)
      SQLite3.__raise(db, status)
      @__topaz_db = nil
      self
    end

    def discard
      @__topaz_db = nil
      self
    end

    def total_changes
      LibSQLite.sqlite3_total_changes(__topaz_db)
    end

    def changes
      LibSQLite.sqlite3_changes(__topaz_db)
    end

    def last_insert_row_id
      LibSQLite.sqlite3_last_insert_rowid(__topaz_db)
    end

    def errmsg
      LibSQLite.sqlite3_errmsg(__topaz_db)
    end

    def errcode
      LibSQLite.sqlite3_errcode(__topaz_db)
    end

    def interrupt
      LibSQLite.sqlite3_interrupt(__topaz_db)
      self
    end

    def complete?(sql)
      LibSQLite.sqlite3_complete(sql.to_s) != 0
    end

    def busy_timeout=(milliseconds)
      SQLite3.__raise(__topaz_db, LibSQLite.sqlite3_busy_timeout(__topaz_db, Integer(milliseconds)))
      milliseconds
    end
    alias busy_timeout busy_timeout=

    # A Ruby busy handler would need a C callback; SQLite waits instead.
    def busy_handler(callable = nil, &block)
      @busy_handler = callable || block
      LibSQLite.sqlite3_busy_timeout(__topaz_db, @busy_handler ? 5000 : 0)
      self
    end

    def statement_timeout=(milliseconds)
      @statement_timeout = milliseconds
    end

    def extended_result_codes=(flag)
      LibSQLite.sqlite3_extended_result_codes(__topaz_db, flag ? 1 : 0)
      flag
    end

    def transaction_active?
      LibSQLite.sqlite3_get_autocommit(__topaz_db) == 0
    end

    def db_filename(database_name)
      LibSQLite.string_at(LibSQLite.sqlite3_db_filename(__topaz_db, database_name.to_s))
    end

    def enable_load_extension(onoff)
      value = onoff == true || onoff == 1 ? 1 : 0
      SQLite3.__raise(__topaz_db, LibSQLite.sqlite3_enable_load_extension(__topaz_db, value))
      self
    end

    def trace(*args, &block)
      raise NotImplementedError, "SQLite3::Database#trace is not supported by topaz's sqlite3"
    end

    def authorizer=(authorizer)
      raise NotImplementedError, "SQLite3::Database#authorizer= is not supported by topaz's sqlite3" if authorizer
      authorizer
    end

    def collation(name, comparator)
      raise NotImplementedError, "SQLite3::Database#collation is not supported by topaz's sqlite3"
    end

    def define_function_with_flags(name, flags, &block)
      raise NotImplementedError, "SQL functions defined in Ruby are not supported by topaz's sqlite3"
    end

    def define_function(name, &block)
      define_function_with_flags(name, 0, &block)
    end

    def disable_quirk_mode
      self
    end

    # Runs every statement in sql; with results_as_hash the rows are
    # hashes.
    def exec_batch(sql, results_as_hash)
      rows = []
      rest = sql.to_s
      until rest.strip.empty?
        statement = Statement.allocate
        rest = statement.__send__(:prepare, self, rest)
        begin
          columns = nil
          while (row = statement.step)
            if results_as_hash
              columns ||= Array.new(statement.column_count) { |i| statement.column_name(i) }
              rows << columns.zip(row).to_h
            else
              rows << row
            end
          end
        ensure
          statement.close unless statement.closed?
        end
      end
      rows
    end

    private

    def open_v2(file, mode, zvfs)
      handle = FFI::MemoryPointer.new(:pointer, 1)
      status = LibSQLite.sqlite3_open_v2(file.to_s, handle, mode, FFI::Pointer::NULL)
      db = handle.get_pointer(0)
      if status != LibSQLite::OK
        message = db.null? ? LibSQLite.sqlite3_errstr(status) : LibSQLite.sqlite3_errmsg(db)
        LibSQLite.sqlite3_close_v2(db) unless db.null?
        SQLite3.__raise(nil, status, nil, message)
      end
      @__topaz_db = db
      self
    end

    def load_extension_internal(file)
      error = FFI::MemoryPointer.new(:pointer, 1)
      status = LibSQLite.sqlite3_load_extension(__topaz_db, file.to_s, FFI::Pointer::NULL, error)
      if status != LibSQLite::OK
        message = LibSQLite.string_at(error.get_pointer(0))
        SQLite3.__raise(__topaz_db, status, nil, message)
      end
      self
    end

    def define_aggregator2(aggregator, name)
      raise NotImplementedError, "SQL aggregates defined in Ruby are not supported by topaz's sqlite3"
    end
  end

  class Statement
    def close
      raise SQLite3::Exception, "cannot use a closed statement" if closed?
      LibSQLite.sqlite3_finalize(@__topaz_st) if @__topaz_st
      @__topaz_st = nil
      @__topaz_empty = false
      self
    end

    # A statement of only whitespace or comments has no handle.
    def closed?
      @__topaz_st.nil? && !@__topaz_empty
    end

    def bind_param(key, value)
      st = __topaz_st
      index = case key
              when Symbol, String
                name = key.to_s
                name = ":#{name}" unless name.start_with?(":")
                LibSQLite.sqlite3_bind_parameter_index(st, name)
              else
                Integer(key)
              end
      raise SQLite3::Exception, "no such bind parameter" if index == 0
      status = case value
               when String
                 if value.is_a?(Blob) || value.encoding == Encoding::ASCII_8BIT
                   LibSQLite.sqlite3_bind_blob(st, index, LibSQLite.buffer(value), value.bytesize, LibSQLite::TRANSIENT)
                 else
                   text = value.encoding == Encoding::UTF_8 || value.encoding == Encoding::US_ASCII ? value : value.encode(Encoding::UTF_8)
                   LibSQLite.sqlite3_bind_text(st, index, LibSQLite.buffer(text), text.bytesize, LibSQLite::TRANSIENT)
                 end
               when Integer
                 if value >= -(2**63) && value < 2**63
                   LibSQLite.sqlite3_bind_int64(st, index, value)
                 else
                   LibSQLite.sqlite3_bind_double(st, index, value.to_f)
                 end
               when Float
                 LibSQLite.sqlite3_bind_double(st, index, value)
               when nil
                 LibSQLite.sqlite3_bind_null(st, index)
               else
                 raise RuntimeError, "can't prepare #{value.class}"
               end
      SQLite3.__raise(__topaz_raw_db, status)
      self
    end

    def reset!
      return self if @__topaz_empty
      LibSQLite.sqlite3_reset(__topaz_st)
      @__topaz_done = false
      self
    end

    def clear_bindings!
      LibSQLite.sqlite3_clear_bindings(__topaz_st)
      @__topaz_done = false
      self
    end

    def step
      return nil if @__topaz_empty
      st = __topaz_st
      return nil if @__topaz_done
      status = LibSQLite.sqlite3_step(st)
      case status
      when LibSQLite::ROW
        count = LibSQLite.sqlite3_column_count(st)
        row = Array.new(count) do |i|
          case LibSQLite.sqlite3_column_type(st, i)
          when LibSQLite::INTEGER
            LibSQLite.sqlite3_column_int64(st, i)
          when LibSQLite::FLOAT
            LibSQLite.sqlite3_column_double(st, i)
          when LibSQLite::TEXT
            length = LibSQLite.sqlite3_column_bytes(st, i)
            pointer = LibSQLite.sqlite3_column_text(st, i)
            text = length == 0 ? +"" : pointer.get_bytes(0, length)
            text.force_encoding(Encoding::UTF_8)
            # Rails sets default_internal to UTF-8, which would only copy
            # the string here.
            internal = Encoding.default_internal
            text = text.encode(internal) if internal && !internal.equal?(Encoding::UTF_8)
            text.freeze
          when LibSQLite::BLOB
            length = LibSQLite.sqlite3_column_bytes(st, i)
            pointer = LibSQLite.sqlite3_column_blob(st, i)
            (length == 0 ? "".b : pointer.get_bytes(0, length).b).freeze
          else
            nil
          end
        end
        row.freeze
      when LibSQLite::DONE
        @__topaz_done = true
        nil
      else
        LibSQLite.sqlite3_reset(st)
        @__topaz_done = false
        SQLite3.__raise(__topaz_raw_db, status)
      end
    end

    def done?
      @__topaz_done ? true : false
    end

    def column_count
      return 0 if @__topaz_empty
      LibSQLite.sqlite3_column_count(__topaz_st)
    end

    def column_name(index)
      name = LibSQLite.sqlite3_column_name(__topaz_st, Integer(index))
      name && name.force_encoding(Encoding::UTF_8).freeze
    end

    def column_decltype(index)
      LibSQLite.string_at(LibSQLite.sqlite3_column_decltype(__topaz_st, Integer(index)))&.freeze
    end

    def bind_parameter_count
      return 0 if @__topaz_empty
      LibSQLite.sqlite3_bind_parameter_count(__topaz_st)
    end

    def sql
      LibSQLite.sqlite3_sql(__topaz_st).force_encoding(Encoding::UTF_8).freeze
    end

    def expanded_sql
      pointer = LibSQLite.sqlite3_expanded_sql(__topaz_st)
      return nil if pointer.null?
      text = pointer.get_string(0).force_encoding(Encoding::UTF_8)
      LibSQLite.sqlite3_free(pointer)
      text.freeze
    end

    def database_name(index)
      LibSQLite.string_at(LibSQLite.sqlite3_column_database_name(__topaz_st, Integer(index)))
    end

    def memused
      LibSQLite.sqlite3_stmt_status(__topaz_st, 99, 0)
    end

    STAT_KEYS = {
      fullscan_steps: 1, sorts: 2, autoindexes: 3, vm_steps: 4, reprepares: 5,
      runs: 6, filter_misses: 7, filter_hits: 8,
    }.freeze

    def stats_as_hash
      STAT_KEYS.to_h { |key, code| [key, LibSQLite.sqlite3_stmt_status(__topaz_st, code, 0)] }
    end

    def stat_for(key)
      code = STAT_KEYS[key] or raise ArgumentError, "unknown key: #{key}"
      LibSQLite.sqlite3_stmt_status(__topaz_st, code, 0)
    end

    private

    def __topaz_st
      raise SQLite3::Exception, "cannot use a closed statement" if @__topaz_st.nil?
      @__topaz_st
    end

    def __topaz_raw_db
      @__topaz_database.__topaz_db
    end

    def prepare(db, sql)
      sql = Topaz.convert_type(sql, String, :to_str)
      @__topaz_database = db
      raw = db.__topaz_db
      text = LibSQLite.buffer(sql)
      handle = FFI::MemoryPointer.new(:pointer, 1)
      tail = FFI::MemoryPointer.new(:pointer, 1)
      status = LibSQLite.sqlite3_prepare_v2(raw, text, sql.bytesize, handle, tail)
      SQLite3.__raise(raw, status, sql)
      @__topaz_st = handle.get_pointer(0)
      @__topaz_done = false
      @__topaz_empty = false
      if @__topaz_st.null?
        # Only whitespace or comments: nothing to run.
        @__topaz_st = nil
        @__topaz_empty = true
      end
      consumed = tail.get_pointer(0).address - text.address
      (sql.byteslice(consumed, sql.bytesize - consumed) || "").force_encoding(Encoding::UTF_8)
    end
  end

  # Copies one database into another (sqlite3_backup_*).
  class Backup
    def initialize(destination, destination_name, source, source_name)
      @destination = destination
      @backup = LibSQLite.sqlite3_backup_init(destination.__topaz_db, destination_name.to_s,
                                              source.__topaz_db, source_name.to_s)
      SQLite3.__raise(destination.__topaz_db, LibSQLite.sqlite3_errcode(destination.__topaz_db)) if @backup.null?
    end

    # Copies up to pages pages (-1 for all); returns the result code
    # (SQLite3::Constants::ErrorCode::DONE once finished).
    def step(pages)
      status = LibSQLite.sqlite3_backup_step(__topaz_backup, Integer(pages))
      unless status == LibSQLite::OK || status == LibSQLite::DONE || status == 5 || status == 6
        SQLite3.__raise(@destination.__topaz_db, status)
      end
      status
    end

    def finish
      LibSQLite.sqlite3_backup_finish(__topaz_backup)
      @backup = nil
      nil
    end

    def remaining
      LibSQLite.sqlite3_backup_remaining(__topaz_backup)
    end

    def pagecount
      LibSQLite.sqlite3_backup_pagecount(__topaz_backup)
    end

    private

    def __topaz_backup
      raise SQLite3::Exception, "backup already finished" if @backup.nil?
      @backup
    end
  end
end
