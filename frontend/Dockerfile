FROM nginx:1.27-alpine
COPY index.html /usr/share/nginx/html/index.html
COPY favicon.ico /usr/share/nginx/html/favicon.ico
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]