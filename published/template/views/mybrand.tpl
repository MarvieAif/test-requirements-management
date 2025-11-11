% rebase('base.tpl', stylesheet='mybrand.css', navigation=False)

% # Compute a single ref once (used for links and scripts)
% tmpRef = '../' if is_doc else ''

<header class="navbar navbar-dark bg-dark navbar-compact sticky-top">
  <div class="container-fluid align-items-center gap-3">

    <!-- Brand (logo + short title) -->
    <a class="navbar-brand d-flex align-items-center gap-2" href="{{tmpRef}}index.html">
      <img src="{{baseurl}}{{tmpRef}}template/aif-portal-logo.png" alt="Logo" class="brand-logo">
      <span class="brand-title">
        % if is_doc:
          {{!doc_attributes.get('name','')}}
        % else:
          Requirements Portal
        % end
      </span>
    </a>

    <!-- Right side: quick links -->
    <ul class="navbar-nav flex-row gap-2">
      % if has_index:
      <li class="nav-item"><a class="nav-link px-2" href="{{ tmpRef }}index.html">Home</a></li>
      % end
      % if has_matrix:
      <li class="nav-item"><a class="nav-link px-2" href="{{ tmpRef }}traceability.html">Traceability</a></li>
      % end
      % if toc:
      <li class="nav-item dropdown d-lg-none">
        <a class="nav-link dropdown-toggle px-2" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
          Contents
        </a>
        <div class="dropdown-menu">
          % for entry in toc:
            <a class="dropdown-item" style="padding-left: {{int(entry['depth'])*12}}px" href="#{{entry['uid']}}">{{!entry['text']}}</a>
          % end
        </div>
      </li>
      % end
    </ul>
  </div>
</header>

<div class="container-fluid">
  <div class="row">
  <aside class="col-lg-3 col-xl-2 d-none d-lg-block">
    % if is_doc:
    <div class="card shadow-sm mb-3">
      <div class="card-header py-2 px-3 fw-semibold">Document</div>
      <div class="card-body py-2 px-3 small d-grid gap-2">
        <div><span class="meta-label">Ref</span> <code class="meta-value">{{doc_attributes.get('ref','-')}}</code></div>
        <div><span class="meta-label">By</span> <code class="meta-value">{{doc_attributes.get('by','-')}}</code></div>
        <div><span class="meta-label">Issue</span> <code class="meta-value">{{doc_attributes.get('major','-')}}{{doc_attributes.get('minor','')}}</code></div>
      </div>
    </div>
    % end

    % if toc:
    <div class="card shadow-sm">
      <div class="card-header py-2 px-3 fw-semibold">Contents</div>
      <div class="card-body py-2 px-3 toc-scroll">
        % for entry in toc:
          % pad = int(entry['depth']) * 12
          <div style="padding-left: {{pad}}px">
            % if entry['uid']:
              <a href="#{{entry['uid']}}">{{!entry['text']}}</a>
            % else:
              <span class="text-muted">{{!entry['text']}}</span>
            % end
          </div>
        % end
      </div>
    </div>
    % end
  </aside>
    <main class="col-lg-9 col-xl-10 py-3">
      <div class="card shadow-sm">
        <div class="card-body">
          <h1 class="h4 mb-3">{{!doc_attributes.get('title','')}}</h1>
          {{!body}}
        </div>
      </div>
    </main>
  </div>
</div>

<script src="{{baseurl}}{{tmpRef}}template/bootstrap.bundle.min.js"></script>
