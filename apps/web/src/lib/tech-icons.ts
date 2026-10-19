/**
 * Ícone da tecnologia (Devicon, versão fixa na CDN). Nome livre da vaga → ícone; sem correspondência → null
 * (a interface mostra só o nome). Mapeamento explícito: melhor sem ícone do que com o ícone errado.
 */
const CDN = "https://cdn.jsdelivr.net/gh/devicons/devicon@v2.16.0/icons";

// chave normalizada → [pasta, arquivo]
const ICONS: Record<string, [string, string]> = {
  python: ["python", "python-original"],
  javascript: ["javascript", "javascript-original"],
  typescript: ["typescript", "typescript-original"],
  java: ["java", "java-original"],
  kotlin: ["kotlin", "kotlin-original"],
  go: ["go", "go-original-wordmark"],
  rust: ["rust", "rust-original"],
  csharp: ["csharp", "csharp-original"],
  dotnet: ["dotnetcore", "dotnetcore-original"],
  cplusplus: ["cplusplus", "cplusplus-original"],
  c: ["c", "c-original"],
  php: ["php", "php-original"],
  ruby: ["ruby", "ruby-original"],
  rails: ["rails", "rails-plain"],
  scala: ["scala", "scala-original"],
  swift: ["swift", "swift-original"],
  dart: ["dart", "dart-original"],
  flutter: ["flutter", "flutter-original"],
  elixir: ["elixir", "elixir-original"],
  r: ["r", "r-original"],
  react: ["react", "react-original"],
  angular: ["angularjs", "angularjs-original"],
  vue: ["vuejs", "vuejs-original"],
  nextjs: ["nextjs", "nextjs-original"],
  nodejs: ["nodejs", "nodejs-original"],
  nestjs: ["nestjs", "nestjs-original"],
  express: ["express", "express-original"],
  django: ["django", "django-plain"],
  flask: ["flask", "flask-original"],
  fastapi: ["fastapi", "fastapi-original"],
  spring: ["spring", "spring-original"],
  laravel: ["laravel", "laravel-original"],
  graphql: ["graphql", "graphql-plain"],
  html: ["html5", "html5-original"],
  css: ["css3", "css3-original"],
  sass: ["sass", "sass-original"],
  tailwind: ["tailwindcss", "tailwindcss-original"],
  postgresql: ["postgresql", "postgresql-original"],
  mysql: ["mysql", "mysql-original"],
  mongodb: ["mongodb", "mongodb-original"],
  redis: ["redis", "redis-original"],
  sqlite: ["sqlite", "sqlite-original"],
  oracle: ["oracle", "oracle-original"],
  sqlserver: ["microsoftsqlserver", "microsoftsqlserver-original"],
  cassandra: ["cassandra", "cassandra-original"],
  elasticsearch: ["elasticsearch", "elasticsearch-original"],
  dynamodb: ["dynamodb", "dynamodb-original"],
  docker: ["docker", "docker-original"],
  kubernetes: ["kubernetes", "kubernetes-plain"],
  terraform: ["terraform", "terraform-original"],
  ansible: ["ansible", "ansible-original"],
  jenkins: ["jenkins", "jenkins-original"],
  git: ["git", "git-original"],
  github: ["github", "github-original"],
  gitlab: ["gitlab", "gitlab-original"],
  githubactions: ["githubactions", "githubactions-original"],
  aws: ["amazonwebservices", "amazonwebservices-original-wordmark"],
  azure: ["azure", "azure-original"],
  gcp: ["googlecloud", "googlecloud-original"],
  linux: ["linux", "linux-original"],
  nginx: ["nginx", "nginx-original"],
  grafana: ["grafana", "grafana-original"],
  prometheus: ["prometheus", "prometheus-original"],
  kafka: ["apachekafka", "apachekafka-original"],
  spark: ["apachespark", "apachespark-original"],
  airflow: ["apacheairflow", "apacheairflow-original"],
  hadoop: ["hadoop", "hadoop-original"],
  pandas: ["pandas", "pandas-original"],
  numpy: ["numpy", "numpy-original"],
  pytorch: ["pytorch", "pytorch-original"],
  tensorflow: ["tensorflow", "tensorflow-original"],
  scikitlearn: ["scikitlearn", "scikitlearn-original"],
  jupyter: ["jupyter", "jupyter-original"],
  rabbitmq: ["rabbitmq", "rabbitmq-original"],
  android: ["android", "android-original"],
  ios: ["apple", "apple-original"],
  figma: ["figma", "figma-original"],
  jest: ["jest", "jest-plain"],
  selenium: ["selenium", "selenium-original"],
  jira: ["jira", "jira-original"],
  bash: ["bash", "bash-original"],
  powershell: ["powershell", "powershell-original"],
};

// sinônimos e variações comuns nas vagas
const ALIASES: Record<string, string> = {
  py: "python",
  js: "javascript",
  ts: "typescript",
  golang: "go",
  "c#": "csharp",
  ".net": "dotnet",
  "dotnetcore": "dotnet",
  "asp.net": "dotnet",
  "c++": "cplusplus",
  rubyonrails: "rails",
  reactjs: "react",
  reactnative: "react",
  angularjs: "angular",
  vuejs: "vue",
  "next.js": "nextjs",
  next: "nextjs",
  node: "nodejs",
  "node.js": "nodejs",
  "nest.js": "nestjs",
  springboot: "spring",
  html5: "html",
  css3: "css",
  tailwindcss: "tailwind",
  postgres: "postgresql",
  mssql: "sqlserver",
  microsoftsqlserver: "sqlserver",
  elastic: "elasticsearch",
  k8s: "kubernetes",
  eks: "kubernetes",
  aks: "kubernetes",
  gke: "kubernetes",
  amazonwebservices: "aws",
  microsoftazure: "azure",
  googlecloud: "gcp",
  googlecloudplatform: "gcp",
  bigquery: "gcp",
  apachekafka: "kafka",
  apachespark: "spark",
  pyspark: "spark",
  apacheairflow: "airflow",
  sklearn: "scikitlearn",
  "scikit-learn": "scikitlearn",
  shell: "bash",
};

const PREFIXES = ["aws", "azure", "gcp", "google cloud", "kafka", "spark", "apache spark", "docker", "kubernetes", "react", "node", "python", "java "];

function key(name: string): string | null {
  const raw = name.trim().toLowerCase();
  if (ALIASES[raw]) return ALIASES[raw];
  const compact = raw.replace(/[\s_-]+/g, "");
  if (ICONS[compact]) return compact;
  if (ALIASES[compact]) return ALIASES[compact];
  const stripped = raw.replace(/\(.*?\)/g, "").replace(/[^a-z0-9+#.]+/g, "");
  if (ICONS[stripped]) return stripped;
  if (ALIASES[stripped]) return ALIASES[stripped];
  // "AWS Glue", "Azure Data Factory", "Kafka Streams" → família
  for (const p of PREFIXES) {
    if (raw.startsWith(p)) return key(p.trim());
  }
  return null;
}

export function techIcon(name: string): string | null {
  const k = key(name);
  const hit = k ? ICONS[k] : undefined;
  return hit ? `${CDN}/${hit[0]}/${hit[1]}.svg` : null;
}
