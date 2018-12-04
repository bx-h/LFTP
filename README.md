# LFTP

#### 运行方法

1. client

   ```python
   python client.py
   ```

   程序运行之后，可以输入进行的操作

   ```python
   lftp lget host:port file
   ```

   ```
   lftp lsend host:port file
   ```


2. Server

   ```python
   python server.py port
   ```


本地测试时，使用127.0.0.1即可

云服务器上测试时，放在云服务器运行的server采用0.0.0.0地址。本地client使用云服务器的公网ip进行访问