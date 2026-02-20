# This Containerfile supports flexible SST and MPICH version building
#
# BUILD ARGUMENTS:
#   SSTrepo: SST repository to use
#   tag:    repository tag name to build from
#   SSTElementsRepo: SST-elements repository to use (optional)
#   elementsTag: SST-elements tag/sha to build from (optional)
#   mpich:  MPICH version  (default: 4.0.2)
#   NCPUS:  Parallel make jobs (default: 2)
#   ENABLE_PERF_TRACKING: Enable performance tracking in SST-core (causes performance hit)
#
# STAGES DEFINED:
#   base       - installs OS + build dependencies + compiles MPICH
#   core-build - builds SST-core
#   full-build - builds SST-elements (optional)

#
# EXAMPLE USAGE:
# Build SST-core only (default):
# podman build \
#   -f Containerfile.tag \
#   --build-arg SSTrepo=https://github.com/sstsimulator/sst-core.git \
#   --build-arg tag=master \
#   --build-arg NCPUS=4 \
#   -t sst-core:latest .
#
# Build SST-core + SST-elements:
# podman build \
#   -f Containerfile.tag \
#   --build-arg SSTrepo=https://github.com/sstsimulator/sst-core.git \
#   --build-arg tag=master \
#   --build-arg SSTElementsRepo=https://github.com/sstsimulator/sst-elements.git \
#   --build-arg elementsTag=master \
#   --build-arg NCPUS=4 \
#   --target full-build \
#   -t sst-full:latest .


# This assumes access to the ubuntu image
FROM ubuntu:22.04 AS base

# Build arguments to control download behavior
ARG mpich=4.0.2
ARG mpich_prefix=mpich-$mpich
ARG NCPUS=2
ARG ENABLE_PERF_TRACKING=

WORKDIR /tmp

# Update and install packages (assumes access to package repositories)
RUN apt update && apt install -y \
    build-essential \
    autoconf \
    automake \
    git \
    gfortran \
    locales \
    python3 \
    python3-dev \
    python3-pip \
    libtool \
    libtool-bin \
    valgrind \
    zlib1g-dev \
    wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Configure UTF-8 locale for unicode character support
RUN locale-gen en_US.UTF-8 \
    && update-locale LANG=en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# Copy MPICH source
COPY ${mpich_prefix}.tar.gz /tmp/

# Build MPICH from source
RUN \
tar xvzf $mpich_prefix.tar.gz                                           && \
cd $mpich_prefix                                                        && \
./configure FFLAGS=-fallow-argument-mismatch FCFLAGS=-fallow-argument-mismatch && \
make -j$NCPUS                                                           && \
make install                                                            && \
make clean                                                              && \
cd ..                                                                   && \
rm -rf $mpich_prefix $mpich_prefix.tar.gz

RUN /sbin/ldconfig

FROM base AS full-build

ARG SSTrepo
ARG tag
ARG SSTElementsRepo
ARG elementsTag
ARG NCPUS=2
ARG ENABLE_PERF_TRACKING

RUN mkdir -p /opt/SST/dev/

# Download SST-core from repo and checkout tag
WORKDIR /workspace
RUN if [ -z "$NCPUS" ]; then \
        export NCPUS=$(($(nproc) / 2)); \
        if [ "$NCPUS" -lt 1 ]; then export NCPUS=1; fi; \
    fi && \
    git clone ${SSTrepo} sst-core && \
    cd sst-core && \
    git checkout ${tag} && \
    ./autogen.sh && \
    mkdir ../build && \
    cd ../build && \
    CONFIGURE_FLAGS="--prefix=/opt/SST/dev"; \
    if [ -n "${ENABLE_PERF_TRACKING}" ]; then \
        CONFIGURE_FLAGS="$CONFIGURE_FLAGS --enable-perf-tracking"; \
        echo "[INFO] Enabling SST performance tracking (will impact performance)"; \
    fi && \
    /workspace/sst-core/configure $CONFIGURE_FLAGS && \
    make -j$NCPUS all && \
    make install && \
    cd /workspace && \
    rm -rf sst-core build

# Download SST-elements from repo and checkout tag
RUN if [ -z "$NCPUS" ]; then \
        export NCPUS=$(($(nproc) / 2)); \
        if [ "$NCPUS" -lt 1 ]; then export NCPUS=1; fi; \
    fi && \
    git clone ${SSTElementsRepo} sst-elements && \
    cd sst-elements && \
    git checkout ${elementsTag} && \
    ./autogen.sh && \
    mkdir ../elements-build && \
    cd ../elements-build && \
    /workspace/sst-elements/configure --prefix=/opt/SST/dev --with-sst-core=/opt/SST/dev && \
    make -j$NCPUS all && \
    make install && \
    cd /workspace && \
    rm -rf sst-elements elements-build

ENV PATH="$PATH:/opt/SST/dev/bin/"
ENV LD_LIBRARY_PATH="/opt/SST/dev/lib:${LD_LIBRARY_PATH}"
WORKDIR /workspace
ENTRYPOINT ["/bin/bash"]

FROM base AS core-build

RUN mkdir -p /opt/SST/dev/

ARG SSTrepo
ARG tag
ARG NCPUS=2
ARG ENABLE_PERF_TRACKING

# Download SST-core from repo and checkout tag
WORKDIR /workspace
RUN if [ -z "$NCPUS" ]; then \
        export NCPUS=$(($(nproc) / 2)); \
        if [ "$NCPUS" -lt 1 ]; then export NCPUS=1; fi; \
    fi && \
    git clone ${SSTrepo} sst-core && \
    cd sst-core && \
    git checkout ${tag} && \
    ./autogen.sh && \
    mkdir ../build && \
    cd ../build && \
    CONFIGURE_FLAGS="--prefix=/opt/SST/dev"; \
    if [ -n "${ENABLE_PERF_TRACKING}" ]; then \
        CONFIGURE_FLAGS="$CONFIGURE_FLAGS --enable-perf-tracking"; \
        echo "[INFO] Enabling SST performance tracking (will impact performance)"; \
    fi && \
    /workspace/sst-core/configure $CONFIGURE_FLAGS && \
    make -j$NCPUS all && \
    make install && \
    cd /workspace && \
    rm -rf sst-core build

ENV PATH="$PATH:/opt/SST/dev/bin/"
ENV LD_LIBRARY_PATH="/opt/SST/dev/lib:${LD_LIBRARY_PATH}"
WORKDIR /workspace
ENTRYPOINT ["/bin/bash"]
