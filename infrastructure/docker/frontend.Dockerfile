FROM nginx:alpine
COPY --chmod=644 infrastructure/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 frontend/dist /usr/share/nginx/html
